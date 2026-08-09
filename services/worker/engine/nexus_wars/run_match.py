"""
Nexus Wars match runner.

Drives the deterministic interpreter for a full match and produces a compact
replay payload (Kaggle-style steps[]). Supports two agent runner backends:

  * InProcessRunner  — wraps a Python callable (used by tests and the
                       built-in random/starter validation opponents).
  * SubprocessRunner — spawns the bot as an external process talking JSON
                       lines over stdin/stdout, optionally wrapped in nsjail
                       for untrusted-code sandboxing (zero network, time/mem
                       limits). This is the production path.

The interpreter logic is reused verbatim; only the agent-calling layer differs.
"""

import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import queue
from types import SimpleNamespace

from nexus_wars import interpreter, Planet, Fleet, BOARD_SIZE, CENTER, SUN_RADIUS


# --------------------------------------------------------------------------
# Configuration + state helpers
# --------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "episodeSteps": 250,
    "actTimeout": 1.0,
    "runTimeout": 510,
    "shipSpeed": 6.0,
    "energyCap": 100,
    "energyRegen": 5,
    "launchEnergyCost": 20,
    "seed": None,
}


def make_env(config):
    env = SimpleNamespace()
    env.configuration = SimpleNamespace(**config)
    env.done = False
    env.info = {}
    return env


def _build_state(num_agents):
    state = []
    for i in range(num_agents):
        s = SimpleNamespace()
        s.observation = SimpleNamespace()
        s.action = None
        s.status = "ACTIVE"
        s.reward = None
        state.append(s)
    return state


def serialize_observation(obs):
    """Convert the internal observation into a JSON-serialisable dict."""
    return {
        "planets": [list(p) for p in getattr(obs, "planets", [])],
        "fleets": [list(f) for f in getattr(obs, "fleets", [])],
        "player": getattr(obs, "player", 0),
        "angular_velocity": getattr(obs, "angular_velocity", 0.0),
        "initial_planets": [list(p) for p in getattr(obs, "initial_planets", [])],
        "next_fleet_id": getattr(obs, "next_fleet_id", 0),
        "step": getattr(obs, "step", 0),
    }


# --------------------------------------------------------------------------
# Agent runners
# --------------------------------------------------------------------------
class InProcessRunner:
    def __init__(self, func):
        self.func = func
        self.dead = False

    def act(self, obs_dict):
        if self.dead:
            return []
        try:
            action = self.func(obs_dict)
            return action if isinstance(action, list) else []
        except Exception:
            self.dead = True
            return []

    def close(self):
        pass


class SubprocessRunner:
    """Spawns an external bot process, talking JSON over stdin/stdout.
    If the bot exceeds `act_timeout` (seconds) for a turn, it is killed and
    subsequent turns return an empty (invalid) action. With `sandbox_cmd` set,
    the bot is launched under nsjail (zero network, time/mem limits).
    """

    def __init__(self, command, act_timeout=0.15, sandbox_cmd=None):
        self.act_timeout = act_timeout
        self.dead = False
        self.is_first_turn = True
        self.consecutive_timeouts = 0
        self._slow = False  # once True, bot gets extra time on all turns
        self._max_adaptive = 3.0
        launch = list(sandbox_cmd) if sandbox_cmd else []
        launch += list(command)
        self.proc = subprocess.Popen(
            launch,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            # New process group so we can kill the entire nsjail tree
            start_new_session=True,
        )

        self.q = queue.Queue()
        def _reader_loop():
            try:
                for line in iter(self.proc.stdout.readline, ''):
                    self.q.put(line)
            except Exception:
                pass
            self.q.put(None)
        self.reader_thread = threading.Thread(target=_reader_loop, daemon=True)
        self.reader_thread.start()

    def act(self, obs_dict):
        if self.dead:
            return []
        try:
            self.proc.stdin.write(json.dumps(obs_dict) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError) as e:
            sys.stdout.write(f"BOT BROKEN PIPE: {e}\n")
            sys.stdout.flush()
            self.dead = True
            return []

        if self.is_first_turn:
            timeout = self._max_adaptive
            self.is_first_turn = False
        elif self._slow:
            timeout = self._max_adaptive
        else:
            timeout = self.act_timeout
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break
            
            try:
                line = self.q.get(timeout=remaining)
            except queue.Empty:
                continue

            if line is None or not line:
                sys.stdout.write(f"BOT TIMEOUT OR EOF: line={line!r}\n")
                sys.stdout.flush()
                self._kill()
                return []
                
            line_str = line.strip()
            if not line_str:
                continue
                
            try:
                action = json.loads(line_str)
                if isinstance(action, dict):
                    action = action.get("action", [])
                if isinstance(action, list):
                    self.consecutive_timeouts = 0
                    return action
            except json.JSONDecodeError:
                continue

        # Timed out this turn
        self.consecutive_timeouts += 1
        self._slow = True
        sys.stdout.write(f"BOT TURN TIMEOUT: {self.consecutive_timeouts}/10\n")
        sys.stdout.flush()
        if self.consecutive_timeouts >= 10:
            sys.stdout.write(f"BOT KILLED (10 consecutive timeouts)\n")
            sys.stdout.flush()
            self._kill()
        return []

    def _kill(self):
        """Kill the bot process and its entire nsjail process group."""
        self.dead = True
        try:
            import signal
            # Kill entire process group (catches nsjail + its children)
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except Exception:
            pass
        try:
            self.proc.kill()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=1)
        except Exception:
            pass

    def close(self):
        """Cleanly shut down the bot process and reap all resources."""
        # Note: must NOT set self.dead here. run_match() calls close() on every
        # runner after the match, so marking dead would make every submission
        # look like a crash (see git history: 822fd59 introduced this bug).
        # 1. Close stdin so bot gets EOF and exits cleanly
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        # 2. Give it a moment to exit on its own
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # 3. SIGTERM the process group first
            try:
                import signal
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except Exception:
                pass
            time.sleep(0.5)
            # 4. SIGKILL entire process group to ensure no zombies
            try:
                import signal
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except Exception:
                pass
            # 5. Final wait to reap the zombie
            try:
                self.proc.wait(timeout=2)
            except Exception:
                pass
        # 6. Close stdout pipe to unblock reader thread
        try:
            self.proc.stdout.close()
        except Exception:
            pass
        # 7. Join reader thread (non-blocking, max 1s)
        try:
            self.reader_thread.join(timeout=1)
        except Exception:
            pass


def make_runner(spec):
    """Build a runner from a spec.

    spec may be:
      * a callable                       -> InProcessRunner
      * "random" / "starter"            -> built-in InProcessRunner
      * {"command": [...], "sandbox": [nsjail args]} -> SubprocessRunner
    """
    if callable(spec):
        return InProcessRunner(spec)
    if isinstance(spec, str):
        from nexus_wars import agents as builtin
        return InProcessRunner(builtin[spec])
    if isinstance(spec, dict) and "command" in spec:
        return SubprocessRunner(
            spec["command"],
            act_timeout=spec.get("actTimeout", 0.15),
            sandbox_cmd=spec.get("sandbox"),
        )
    raise ValueError(f"Unsupported agent spec: {spec!r}")


# --------------------------------------------------------------------------
# Match execution
# --------------------------------------------------------------------------
def run_match(runners, config=None, seed=None):
    config = {**DEFAULT_CONFIG, **(config or {})}
    if seed is not None:
        config["seed"] = seed
    num_agents = len(runners)
    env = make_env(config)
    state = _build_state(num_agents)

    # Initialise (env.reset equivalent).
    interpreter(state, env)
    seed_used = env.info.get("seed")

    steps = []
    step = 0
    max_steps = config["episodeSteps"]
    match_start = time.time()

    while not env.done and step < max_steps:
        obs0 = state[0].observation
        obs0.step = step

        actions = []
        for i in range(num_agents):
            obs_dict = serialize_observation(state[i].observation)
            obs_dict["player"] = i
            actions.append(runners[i].act(obs_dict))
            state[i].action = actions[-1]

        interpreter(state, env)

        steps.append({
            "observation": serialize_observation(state[0].observation),
            "action": [list(a) if isinstance(a, list) else a for a in actions],
            "reward": [s.reward for s in state],
            "status": [s.status for s in state],
            "log": [],
        })

        step += 1
        if time.time() - match_start > config["runTimeout"]:
            env.done = True
            for s in state:
                if s.status == "ACTIVE":
                    s.status = "DONE"

    for r in runners:
        r.close()

    # Final result.
    scores = [0] * num_agents
    obs0 = state[0].observation
    for p in getattr(obs0, "planets", []):
        if p[1] != -1:
            scores[p[1]] += p[5]
    for f in getattr(obs0, "fleets", []):
        scores[f[1]] += f[6]

    winner = None
    reason = "steps"
    alive = set()
    for p in getattr(obs0, "planets", []):
        if p[1] != -1:
            alive.add(p[1])
    for f in getattr(obs0, "fleets", []):
        alive.add(f[1])
    if len(alive) <= 1:
        reason = "elimination"
        if alive:
            winner = next(iter(alive))
    else:
        max_score = max(scores)
        if max_score > 0 and scores.count(max_score) == 1:
            winner = scores.index(max_score)

    replay = {
        "version": "1.0",
        "engine": "nexus_wars",
        "engineVersion": "2026.1.0",
        "seed": seed_used,
        "configuration": config,
        "players": [{"playerId": i} for i in range(num_agents)],
        "steps": steps,
        "info": {
            "winner": winner,
            "reason": reason,
            "scores": scores,
            "durationMs": int((time.time() - match_start) * 1000),
            "steps": len(steps),
        },
    }
    return replay


# --------------------------------------------------------------------------
# CLI for local testing
# --------------------------------------------------------------------------
def _main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--agents", nargs=2, default=["random", "starter"])
    ap.add_argument("--out", default="replay.json")
    ap.add_argument("--episodeSteps", type=int, default=250)
    args = ap.parse_args(argv)

    config = dict(DEFAULT_CONFIG)
    config["episodeSteps"] = args.episodeSteps
    runners = [make_runner(a) for a in args.agents]
    replay = run_match(runners, config, seed=args.seed)
    with open(args.out, "w") as f:
        json.dump(replay, f)
    print(f"seed={replay['seed']} steps={replay['info']['steps']} "
          f"winner={replay['info']['winner']} reason={replay['info']['reason']} "
          f"scores={replay['info']['scores']} durationMs={replay['info']['durationMs']}")


if __name__ == "__main__":
    _main(sys.argv[1:])
