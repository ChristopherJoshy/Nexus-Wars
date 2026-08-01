import sys
import os
import random

sys.path.insert(0, os.path.abspath('services/worker/engine'))
sys.path.insert(0, os.path.abspath('test-bots/personal_agent'))
from nexus_wars.run_match import make_runner, run_match
from nexus_wars.agents import agents as builtin

import chris

def chris_agent(obs):
    try:
        if "observation" in obs: obs = obs["observation"]
        return chris.agent_fn(obs)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return []

def main():
    opp_name = "random"
    opp = builtin[opp_name]
    seed = 1234
    
    print(f"Running match against {opp_name} (seed {seed})...")
    res = run_match([make_runner(chris_agent), make_runner(opp)], seed=seed, config={"episodeSteps": 500})
    print("Match finished. Steps:", len(res["steps"]))
    print("Winner:", res["info"].get("winner"))
    
if __name__ == "__main__":
    main()
