"""Benchmark chris.py v6 against all test bots using InProcessRunner."""
import random, sys, json
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match

# Import chris agent directly
sys.path.insert(0, 'test-bots/personal_agent')
import chris as chris_module

chris_path = 'test-bots/personal_agent/chris.py'
opponents = {
    'random': 'test-bots/random',
    'fortress': 'test-bots/fortress.py',
    'viper': 'test-bots/viper.py',
    'chimera': 'test-bots/chimera.py',
    'chimera-np': 'test-bots/chimera-np.py',
}

def chris_agent(obs):
    """Wrapper to call chris module."""
    try:
        return chris_module.agent_fn(obs)
    except Exception:
        return []

random.seed(99)
seeds = [random.randint(1, 9999999) for _ in range(25)]
results = {}

for name, opp in opponents.items():
    wins = 0
    total = 0
    for s in seeds:
        # chris as P0
        r0 = run_match([
            make_runner(chris_agent),
            make_runner(opp)
        ], seed=s)
        total += 1
        if r0['info']['winner'] == 0:
            wins += 1
        # chris as P1
        r1 = run_match([
            make_runner(opp),
            make_runner(chris_agent)
        ], seed=s)
        total += 1
        if r1['info']['winner'] == 1:
            wins += 1
    results[name] = {'wins': wins, 'total': total, 'rate': wins/total}

print(json.dumps(results, indent=2))
