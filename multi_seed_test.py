#!/usr/bin/env python3
import sys, os, time, random

ENGINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "services/worker/engine/nexus_wars")
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-bots", "personal_agent"))

import nexus_wars as engine
import run_match
import chris

def run_one(seed, player_position, n_steps=50):
    runner_chris = run_match.InProcessRunner(chris.agent)
    runner_rand = run_match.InProcessRunner(engine.agents["random"])
    if player_position == 0:
        runners = [runner_chris, runner_rand]
    else:
        runners = [runner_rand, runner_chris]
    replay = run_match.run_match(
        runners=runners,
        config={"seed": seed, "actTimeout": 1.0, "runTimeout": 120,
                "episodeSteps": n_steps, "shipSpeed": 6.0, "energyCap": 100,
                "energyRegen": 5, "launchEnergyCost": 20},
        seed=seed,
    )
    info = replay["info"]
    chris_idx = player_position
    chris_dead = runners[chris_idx].dead
    won = info["winner"] == chris_idx
    action_count = sum(len(s["action"][chris_idx]) for s in replay["steps"])
    return {
        "seed": seed, "pos": player_position, "winner": info["winner"],
        "won": won, "scores": info["scores"], "steps": info["steps"],
        "dead": chris_dead, "action_count": action_count,
        "duration_ms": info["durationMs"],
    }

seeds = [42, 123, 7, 999, 2024]
results = []
for seed in seeds:
    for pos in [0, 1]:
        r = run_one(seed, pos)
        results.append(r)
        status = "DEAD" if r["dead"] else "alive"
        print("seed=%d pos=%d winner=%s won=%s scores=%s steps=%d %s actions=%d dur=%dms" % (
            r["seed"], r["pos"], r["winner"], r["won"], r["scores"], r["steps"], status, r["action_count"], r["duration_ms"]))

print("\n=== Summary ===")
print("Total: %d" % len(results))
print("Dead: %d/%d" % (sum(1 for r in results if r["dead"]), len(results)))
print("Wins: %d/%d (%.0f%%)" % (sum(1 for r in results if r["won"]), len(results), sum(1 for r in results if r["won"])/len(results)*100))
print("Survived 1+ steps: %d/%d" % (sum(1 for r in results if r["steps"] >= 1), len(results)))
print("Avg actions/match: %.1f" % (sum(r["action_count"] for r in results)/len(results)))
