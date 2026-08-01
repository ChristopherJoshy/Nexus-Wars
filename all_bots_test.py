#!/usr/bin/env python3
import sys, os, json, io, importlib.util, random

ENGINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services/worker/engine/nexus_wars")
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-bots", "personal_agent"))

import nexus_wars as engine
import run_match
import chris

TESTBOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-bots")

def load_bot(filepath):
    spec = importlib.util.spec_from_file_location("bot_" + os.path.basename(filepath)[:-3], filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def wrap_main_bot(filepath):
    mod = load_bot(filepath)
    def act(obs_dict):
        old_in, old_out = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(json.dumps(obs_dict))
        sys.stdout = io.StringIO()
        try:
            mod.main()
        finally:
            output = sys.stdout.getvalue()
            sys.stdin, sys.stdout = old_in, old_out
        try:
            return json.loads(output.strip())
        except:
            return []
    return act

opponents = {}
opponents["random"] = engine.agents["random"]
opponents["starter"] = engine.agents["starter"]
opponents["fortress"] = wrap_main_bot(os.path.join(TESTBOTS_DIR, "fortress.py"))
opponents["viper"] = wrap_main_bot(os.path.join(TESTBOTS_DIR, "viper.py"))
opponents["chimera"] = wrap_main_bot(os.path.join(TESTBOTS_DIR, "chimera.py"))
chimera_np = load_bot(os.path.join(TESTBOTS_DIR, "chimera-np.py"))
opponents["chimera-np"] = chimera_np.decide

print("Available opponents:", list(opponents.keys()))
print()

seeds = [42, 123, 7]
all_results = {}

for opp_name, opp_fn in opponents.items():
    for pos in [0, 1]:
        results = []
        for seed in seeds:
            runner_chris = run_match.InProcessRunner(chris.agent)
            runner_opp = run_match.InProcessRunner(opp_fn)
            if pos == 0:
                runners = [runner_chris, runner_opp]
            else:
                runners = [runner_opp, runner_chris]
            replay = run_match.run_match(
                runners=runners,
                config={"seed": seed, "actTimeout": 1.0, "runTimeout": 60,
                        "episodeSteps": 30, "shipSpeed": 6.0, "energyCap": 100,
                        "energyRegen": 5, "launchEnergyCost": 20},
                seed=seed,
            )
            info = replay["info"]
            dead = runners[pos].dead
            won = info["winner"] == pos
            results.append({"won": won, "dead": dead, "scores": info["scores"],
                            "steps": info["steps"], "dur": info["durationMs"]})
        won_count = sum(1 for r in results if r["won"])
        dead_count = sum(1 for r in results if r["dead"])
        survive = sum(1 for r in results if not r["dead"] and r["steps"] >= 1)
        avg_dur = sum(r["dur"] for r in results) / len(results)
        all_results[(opp_name, pos)] = (won_count, dead_count, survive, len(results), avg_dur/1000)
        print("vs %-12s P%d: %d/%d wins, %d dead, %d survived, avg %.1fs" % (
            opp_name, pos, won_count, len(results), dead_count, survive, avg_dur/1000))

print()
print("=" * 60)
print("TOTALS")
print("=" * 60)
total_wins = sum(r[0] for r in all_results.values())
total_matches = sum(r[3] for r in all_results.values())
total_dead = sum(r[1] for r in all_results.values())
total_surv = sum(r[2] for r in all_results.values())
print("%d/%d wins, %d dead, %d/%d survived" % (total_wins, total_matches, total_dead, total_surv, total_matches))
