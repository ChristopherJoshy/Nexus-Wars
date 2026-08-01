import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

_PROC = None
_PROC_STARTS = 0
_STARTED = time.perf_counter()
_SYSTEM_LOGGED = False
_FAILURE_LOGS = 0
_MAX_FAILURE_LOGS = 3
_CHILD_LOG_LINES = 0


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


_LOG_EVERY = _int_env("AGENT_LOG_EVERY", 1)
_MAX_CHILD_LOG_LINES = _int_env("AGENT_MAX_CHILD_LOG_LINES", 200)


def _obs_value(obs, key, default=None):
    if obs is None:
        return default
    if isinstance(obs, dict):
        return obs.get(key, default)
    return getattr(obs, key, default)


def _config_value(configuration, key):
    if configuration is None:
        return None
    if isinstance(configuration, dict):
        return configuration.get(key)
    return getattr(configuration, key, None)


def _agent_cli_path(configuration):
    raw_path = _config_value(configuration, "__raw_path__")
    roots = []
    if raw_path:
        raw = Path(raw_path).resolve()
        roots.append(raw.parent if raw.is_file() else raw)
    if "__file__" in globals():
        roots.append(Path(__file__).resolve().parent)
    roots.append(Path.cwd())
    roots.append(Path("/kaggle_simulations/agent"))

    for root in roots:
        path = root / "agent_cli"
        if path.exists():
            return path
    return roots[0] / "agent_cli"


def _ensure_process(configuration):
    global _PROC, _PROC_STARTS
    if _PROC is not None and _PROC.poll() is None:
        return _PROC

    path = _agent_cli_path(configuration)
    try:
        os.chmod(path, 0o755)
    except OSError:
        pass
    _PROC = subprocess.Popen(
        [str(path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(path.parent),
    )
    _PROC_STARTS += 1
    if _PROC.stderr is not None:
        threading.Thread(target=_forward_child_stderr, args=(_PROC,), daemon=True).start()
    return _PROC


def _forward_child_stderr(proc):
    global _CHILD_LOG_LINES
    try:
        for raw_line in proc.stderr:
            line = raw_line.rstrip()
            if not line:
                continue
            if _CHILD_LOG_LINES >= _MAX_CHILD_LOG_LINES:
                continue
            _CHILD_LOG_LINES += 1
            print(f"agent_child {line[:1000]}", flush=True)
    except Exception as exc:
        if _CHILD_LOG_LINES < _MAX_CHILD_LOG_LINES:
            _CHILD_LOG_LINES += 1
            print(f"agent_child stderr_forwarder_error={exc!r}", flush=True)


def _log_failure(message, proc=None, exc=None):
    global _FAILURE_LOGS
    if _FAILURE_LOGS >= _MAX_FAILURE_LOGS:
        return
    _FAILURE_LOGS += 1

    detail = message
    if proc is not None:
        detail += f" proc_returncode={proc.poll()}"
        if proc.poll() is not None and proc.stderr is not None:
            try:
                err = proc.stderr.read()
            except Exception as stderr_exc:
                err = f"<stderr read failed: {stderr_exc!r}>"
            if err:
                detail += f" proc_stderr={err.strip()[:1000]!r}"
    if exc is not None:
        detail += f" exc={exc!r}"
    print(f"agent_error {detail}", file=sys.stderr)


def _memory_mb():
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size / (1024 * 1024))
    except (AttributeError, OSError, ValueError):
        return None


def _nproc():
    try:
        return len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        return os.cpu_count()


def _format_float(value):
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "na"


def _format_ms(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "na"


def _datetime_delta_ms(later, earlier):
    if later is None or earlier is None:
        return None
    return (later - earlier).total_seconds() * 1000.0


def _format_utc(value):
    try:
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except Exception:
        return "na"


def _log_system(configuration):
    global _SYSTEM_LOGGED
    if _SYSTEM_LOGGED:
        return
    _SYSTEM_LOGGED = True

    mem_mb = _memory_mb()
    print(
        "agent_sys "
        f"pid={os.getpid()} cli_pid={getattr(_PROC, 'pid', 'na')} "
        f"nproc={_nproc()} os_cpu_count={os.cpu_count()} "
        f"system={platform.system()} release={platform.release()} "
        f"machine={platform.machine()} python={sys.version.split()[0]} "
        f"mem_mb={mem_mb if mem_mb is not None else 'na'} "
        f"episode_steps={_config_value(configuration, 'episodeSteps')} "
        f"act_timeout_s={_config_value(configuration, 'actTimeout')} "
        f"agent_timeout_s={_config_value(configuration, 'agentTimeout')}",
    )


def _log_step(obs, configuration, started, started_at):
    if _LOG_EVERY <= 0:
        return

    try:
        finished_at = datetime.now(timezone.utc)
        wall_elapsed_ms = _datetime_delta_ms(finished_at, started_at)

        step = _obs_value(obs, "step", 0) or 0
        try:
            step_int = int(step)
        except (TypeError, ValueError):
            step_int = 0
        if step_int == 0:
            _log_system(configuration)
        if step_int % _LOG_EVERY != 0:
            return

        print(
            "agent_step "
            f"wall_dt_ms={_format_ms(wall_elapsed_ms)} "
            f"remaining_overage_s={_format_float(_obs_value(obs, 'remainingOverageTime'))} "
            f"total_elapsed_s={time.perf_counter() - _STARTED:.2f}",
        )
    except Exception:
        pass


def _configuration_payload(configuration):
    payload = {}
    for key in ("episodeSteps", "actTimeout", "agentTimeout", "shipSpeed", "cometSpeed", "seed"):
        value = _config_value(configuration, key)
        if value is not None:
            payload[key] = value
    return payload


def _payload(obs, configuration):
    return {
        "observation": dict(obs) if not isinstance(obs, dict) else obs,
        "configuration": _configuration_payload(configuration),
    }


def agent(obs, configuration=None):
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    action = []
    proc = None
    try:
        proc = _ensure_process(configuration)
        if proc.stdin is not None and proc.stdout is not None:
            line = json.dumps(_payload(obs, configuration), separators=(",", ":"))
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            response = proc.stdout.readline()
            if response:
                try:
                    parsed = json.loads(response)
                    if isinstance(parsed, list):
                        action = parsed
                    else:
                        _log_failure(f"non-list response={response.strip()[:200]!r}", proc=proc)
                except Exception as exc:
                    _log_failure(f"invalid json response={response.strip()[:200]!r}", proc=proc, exc=exc)
            else:
                _log_failure("empty response from agent_cli", proc=proc)
    except Exception as exc:
        _log_failure("wrapper exception", proc=proc, exc=exc)
    _log_step(obs, configuration, started, started_at)
    return action
