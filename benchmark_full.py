"""Run both-position 25-seed benchmark for v10 hybrid agent against all 8 local opponents.

Uses InProcessRunner only (SubprocessRunner broken on Windows — OSError: [Errno 22]).
"""
import os, sys, random, json
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match

sys.path.insert(0, os.path.dirname(__file__))
import benchmark_agents as ba
sys.path.insert(0, 'test-bots/personal_agent')
import chrisv99 as chris_module

def chris_agent(obs):
    try:
        return chris_module.agent_fn(obs)
    except Exception:
        return []

random.seed(234917)  # fresh seed, no reuse
seeds = [random.randint(1, 9999999) for _ in range(25)]
opponents = {
    'random': ba.agent_random,
}

results = {}
for name, opp in opponents.items():
    wins = 0
    total = 0
    for s in seeds:
        r0 = run_match([make_runner(chris_agent), make_runner(opp)], seed=s)
        total += 1
        if r0['info'].get('winner') == 0:
            wins += 1
        r1 = run_match([make_runner(opp), make_runner(chris_agent)], seed=s)
        total += 1
        if r1['info'].get('winner') == 1:
            wins += 1
    results[name] = {'wins': wins, 'total': total, 'rate': wins/total}
    print(f"  {name}: {wins}/{total} = {wins/total:.3f}")

print(json.dumps(results, indent=2))
