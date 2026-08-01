import os, sys, random, json
sys.path.insert(0, 'services/worker/engine')
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, 'test-bots/personal_agent')
sys.path.insert(0, 'extracted_agents')

import chrisv99 as chris_module
import Rank1_AEGIS_Bot1_aethon as opp_module

def chris_agent(obs):
    try: return chris_module.agent_fn(obs)
    except Exception: return []

def opp_agent(obs):
    try: return opp_module.agent_fn(obs)
    except Exception: return []

s = 100
print(f"Seed {s} (P0=chris, P1=opp)...")
r0 = run_match([make_runner(chris_agent), make_runner(opp_agent)], seed=s)
print("Winner:", r0['info'].get('winner'))

print(f"Seed {s} (P0=opp, P1=chris)...")
r1 = run_match([make_runner(opp_agent), make_runner(chris_agent)], seed=s)
print("Winner:", r1['info'].get('winner'))
