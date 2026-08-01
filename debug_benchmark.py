"""Debug benchmark with detailed output."""
import os, sys, random, json
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match

sys.path.insert(0, os.path.dirname(__file__))
import benchmark_agents as ba
sys.path.insert(0, 'test-bots/personal_agent')
import chris as chris_module

def chris_agent(obs):
    try:
        return chris_module.agent_fn(obs)
    except Exception:
        return []

random.seed(99)
seeds = [random.randint(1, 9999999) for _ in range(3)]

for i, s in enumerate(seeds):
    print(f'\n=== Seed {s} ===')
    r0 = run_match([
        make_runner(chris_agent),
        make_runner(ba.agent_fortress)
    ], seed=s)
    print(f'Chris P0 vs Fortress P1: winner={r0["info"]["winner"]}, scores={r0["info"]["scores"]}, steps={r0["info"]["steps"]}')

    r1 = run_match([
        make_runner(ba.agent_fortress),
        make_runner(chris_agent)
    ], seed=s)
    print(f'Fortress P0 vs Chris P1: winner={r1["info"]["winner"]}, scores={r1["info"]["scores"]}, steps={r1["info"]["steps"]}')
