"""Verify opponent strength by testing fortress vs random."""
import os, sys, random, json
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match

sys.path.insert(0, os.path.dirname(__file__))
import benchmark_agents as ba

random.seed(42)
seeds = [random.randint(1, 9999999) for _ in range(5)]

fortress_wins = 0
for s in seeds:
    r0 = run_match([make_runner("random"), make_runner(ba.agent_fortress)], seed=s)
    if r0['info']['winner'] == 1:
        fortress_wins += 1
    print(f'Seed {s}: random vs fortress -> winner={r0["info"]["winner"]}, scores={r0["info"]["scores"]}')

print(f'Fortress win rate vs random: {fortress_wins}/{len(seeds)}')
