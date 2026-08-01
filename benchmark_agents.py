"""In-process agent wrappers for local benchmarking."""
import json, math, sys
from typing import Any, Dict, List

# Import opponent modules directly
import importlib.util, pathlib

def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_BASE = pathlib.Path(__file__).parent / "test-bots"
_DOWNLOADS = pathlib.Path("C:/Users/chris/Downloads")

fortress_mod = _load_module("fortress", str(_BASE / "fortress.py"))
viper_mod = _load_module("viper", str(_BASE / "viper.py"))
chimera_mod = _load_module("chimera", str(_BASE / "chimera.py"))
chimera_np_mod = _load_module("chimera_np", str(_BASE / "chimera-np.py"))

# Load Downloads bots
# downloads_agent_mod = _load_module("downloads_agent", str(_DOWNLOADS / "agent.py"))
# downloads_agent_1_mod = _load_module("downloads_agent_1", str(_DOWNLOADS / "agent (1).py"))

# Try loading numpy for chimera-np and downloads agent (1)
try:
    import numpy as _np
    _HAS_NP = True
except Exception:
    _HAS_NP = False

def _call_bot(mod, obs):
    import io
    old_stdout = sys.stdout
    old_stdin = sys.stdin
    buf = io.StringIO()
    sys.stdout = buf
    sys.stdin = io.StringIO(json.dumps(obs) + "\n")
    try:
        mod.main()
    except Exception:
        pass
    sys.stdout = old_stdout
    sys.stdin = old_stdin
    out = buf.getvalue().strip()
    if not out:
        return []
    try:
        obj = json.loads(out.splitlines()[-1])
    except Exception:
        return []
    return obj if isinstance(obj, list) else []

# Wrapper functions for InProcessRunner
def agent_random(obs):
    from nexus_wars import agents
    return agents["random"](obs)

def agent_starter(obs):
    from nexus_wars import agents
    return agents["starter"](obs)

def agent_fortress(obs):
    return _call_bot(fortress_mod, obs)

def agent_viper(obs):
    return _call_bot(viper_mod, obs)

def agent_chimera(obs):
    return _call_bot(chimera_mod, obs)

def agent_chimera_np(obs):
    if not _HAS_NP:
        return []
    return _call_bot(chimera_np_mod, obs)

def agent_downloads(obs):
    """Downloads agent.py — stdlib only, fractional launches, endgame rush, sun r=11.5."""
    return _call_bot(downloads_agent_mod, obs)

def agent_downloads_1(obs):
    """Downloads agent (1).py — numpy, orbital drift prediction, RESERVE_MIN=8, sun r=11.0."""
    if not _HAS_NP:
        return []
    return _call_bot(downloads_agent_1_mod, obs)
