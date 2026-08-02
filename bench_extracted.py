import importlib.util
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "services", "worker", "engine", "nexus_wars"))
from run_match import make_runner, run_match

EXTRACTED = os.path.join(os.path.dirname(__file__), "extracted_agents")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BotHandle:
    def __init__(self, label, fn):
        self.label = label
        self.fn = fn
        self.turns = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.timeouts = 0

    def act(self, obs):
        t0 = time.monotonic()
        try:
            out = self.fn(obs)
            out = out if isinstance(out, list) else []
        except Exception:
            out = []
        dt = (time.monotonic() - t0) * 1000.0
        self.turns += 1
        self.total_ms += dt
        if dt > self.max_ms:
            self.max_ms = dt
        if dt > 150.0:
            self.timeouts += 1
        return out

    def reset(self):
        self.turns = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.timeouts = 0


def make_skywalker():
    mod = load_module("skywalker", os.path.join(EXTRACTED, "Rank3_Skywalker_Bot_agent.py"))
    return BotHandle("skywalker", mod.act)


def make_mountain():
    mod = load_module("mountain", os.path.join(EXTRACTED, "Rank2_ODYSSEY_Bot_mountain.py"))
    cmd = mod.Mountain()
    return BotHandle("mountain", lambda obs: cmd.act(obs, time.monotonic() + 0.12))


def make_abomination():
    mod = load_module("abomination", os.path.join(EXTRACTED, "Rank1_Raggitar_Bot_abomination_ultra.py"))
    cmd = mod.AbominationUltra()
    return BotHandle("abomination", lambda obs: cmd.act(obs, time.monotonic() + 0.12))


FACTORIES = {
    "skywalker": make_skywalker,
    "mountain": make_mountain,
    "abomination": make_abomination,
}


def make_builtin(name):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
    import benchmark_agents as ba
    fns = {
        "random": ba.agent_random,
        "starter": ba.agent_starter,
        "fortress": ba.agent_fortress,
        "viper": ba.agent_viper,
        "chimera": ba.agent_chimera,
        "chimera_np": ba.agent_chimera_np,
    }
    return BotHandle(name, fns[name])


def load_handles(names):
    handles = {}
    for n in names:
        if n in FACTORIES:
            handles[n] = FACTORIES[n]()
        elif n in ("random", "starter", "fortress", "viper", "chimera", "chimera_np"):
            handles[n] = make_builtin(n)
        else:
            path = os.path.abspath(n)
            mod = load_module("custom_" + os.path.basename(path), path)
            if hasattr(mod, "Commander"):
                cmd = mod.Commander()
                handles[n] = BotHandle(n, lambda obs, cmd=cmd: cmd.act(obs, time.monotonic() + 0.12))
            elif hasattr(mod, "Mountain"):
                cmd = mod.Mountain()
                handles[n] = BotHandle(n, lambda obs, cmd=cmd: cmd.act(obs, time.monotonic() + 0.12))
            elif hasattr(mod, "AbominationUltra"):
                cmd = mod.AbominationUltra()
                handles[n] = BotHandle(n, lambda obs, cmd=cmd: cmd.act(obs, time.monotonic() + 0.12))
            else:
                handles[n] = BotHandle(n, mod.act)
    return handles


def play(a, b, seed):
    r = run_match([make_runner(a.act), make_runner(b.act)], seed=seed)
    info = r["info"]
    return info.get("winner"), info.get("reason"), info.get("scores")


def bench(names, seeds, n_matches=None):
    handles = load_handles(names)
    results = {}
    for a in names:
        for b in names:
            if a == b:
                continue
            key = (a, b)
            wins = 0
            total = 0
            for s in seeds:
                handles[a].reset()
                handles[b].reset()
                w, reason, scores = play(handles[a], handles[b], s)
                total += 1
                if w == 0:
                    wins += 1
                handles[a].reset()
                handles[b].reset()
                w2, reason2, scores2 = play(handles[b], handles[a], s)
                total += 1
                if w2 == 1:
                    wins += 1
            results[key] = {"wins": wins, "total": total, "rate": wins / total}
    return results, handles


if __name__ == "__main__":
    names = sys.argv[1:] if len(sys.argv) > 1 else ["skywalker", "mountain", "abomination"]
    n_seeds = int(os.environ.get("SEEDS", "6"))
    random.seed(12345)
    seeds = [random.randint(1, 9999999) for _ in range(n_seeds)]
    results, handles = bench(names, seeds)
    for (a, b), v in sorted(results.items()):
        print(f"{a} vs {b}: {v['wins']}/{v['total']} = {v['rate']:.3f}")
    print("--- timing (avg ms / max ms / >150ms turns) ---")
    for n in names:
        h = handles[n]
        avg = h.total_ms / max(1, h.turns)
        print(f"{n}: avg={avg:.1f}ms max={h.max_ms:.1f}ms slow={h.timeouts}")
