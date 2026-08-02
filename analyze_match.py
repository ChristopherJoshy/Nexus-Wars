import importlib.util
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


def make_commander(name, path, cls):
    mod = load_module(name, path)
    cmd = mod.Commander() if hasattr(mod, "Commander") else mod.__dict__[cls]()
    return lambda obs: cmd.act(obs, time.monotonic() + 0.12)


def analyze(seed, a_fn, b_fn):
    r = run_match([make_runner(a_fn), make_runner(b_fn)], seed=seed)
    info = r["info"]
    steps = r["steps"]
    winner = info.get("winner")
    final = steps[-1]["observation"] if steps else {}
    planets = final.get("planets", [])
    scores = [0, 0]
    for p in planets:
        if p[1] != -1:
            scores[p[1]] += p[5]
    return winner, info.get("reason"), scores, steps


def ownership_timeline(steps):
    owners = {0: {}, 1: {}}
    for t, st in enumerate(steps):
        for p in st["observation"]["planets"]:
            if p[1] != -1:
                owners[p[1]].setdefault(p[0], t)
    return owners


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--name", default="best")
    ap.add_argument("--path", default="extracted_agents/best.py")
    ap.add_argument("--opp", default="mountain")
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    opp_path = os.path.join(EXTRACTED, "Rank2_ODYSSEY_Bot_mountain.py")
    if args.opp == "abomination":
        opp_path = os.path.join(EXTRACTED, "Rank1_Raggitar_Bot_abomination_ultra.py")
    elif args.opp == "skywalker":
        opp_path = os.path.join(EXTRACTED, "Rank3_Skywalker_Bot_agent.py")

    a_fn = make_commander(args.name, os.path.abspath(args.path), "Commander")
    if args.opp == "skywalker":
        mod = load_module("skywalker", opp_path)
        b_fn = mod.act
    else:
        b_fn = make_commander(args.opp, opp_path, "Mountain" if args.opp == "mountain" else "AbominationUltra")

    random.seed(777)
    seeds = [random.randint(1, 9999999) for _ in range(args.seeds)]
    for s in seeds:
        w, reason, scores, steps = analyze(s, a_fn, b_fn)
        ow = ownership_timeline(steps)
        a_first = min(ow[0].values()) if ow[0] else None
        b_first = min(ow[1].values()) if ow[1] else None
        print(f"seed={s} winner={w} reason={reason} scores={scores} "
              f"first_planets p0@t{a_first} p1@t{b_first} len={len(steps)}")
        if args.trace and len(steps) >= 500:
            for idx in range(0, 100, 10):
                st = steps[idx]
                obs = st["observation"]
                sp = [0, 0]
                nplan = [0, 0]
                for p in obs["planets"]:
                    if p[1] != -1:
                        sp[p[1]] += p[5]
                        nplan[p[1]] += 1
                nf = [0, 0]
                for f in obs["fleets"]:
                    nf[f[1]] += f[6]
                act = st["action"]
                print(f"  t={obs['step']} p0ships={sp[0]}({nplan[0]}p,{nf[0]}f) "
                      f"p1ships={sp[1]}({nplan[1]}p,{nf[1]}f) "
                      f"n0={len(act[0]) if isinstance(act[0],list) else act[0]} "
                      f"n1={len(act[1]) if isinstance(act[1],list) else act[1]}")
            last_100 = steps[-100:]
            for st in last_100:
                obs = st["observation"]
                sp = [0, 0]
                for p in obs["planets"]:
                    if p[1] != -1:
                        sp[p[1]] += p[5]
                act = st["action"]
                print(f"  t={st['observation']['step']} p0ships={sp[0]} p1ships={sp[1]} "
                      f"acts0={act[0] if isinstance(act[0], list) else act[0]} "
                      f"acts1={act[1] if isinstance(act[1], list) else act[1]}")


if __name__ == "__main__":
    main()
