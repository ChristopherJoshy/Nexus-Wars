import os
import sys
import glob

# Setup paths
sys.path.insert(0, 'services/worker/engine')
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match

sys.path.insert(0, 'test-bots/personal_agent')
import chrisv99

import importlib.util

def load_agent(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    def wrapped(obs):
        try: return mod.agent_fn(obs)
        except Exception: return []
    return wrapped

def run_tournament():
    opponents = sorted(glob.glob(os.path.join("extracted_agents", "*.py")))
    chris_path = os.path.join("test-bots", "personal_agent", "chrisv99.py")
    chris_agent = load_agent(chris_path)
    
    print(f"Starting tournament: chrisv99.py vs {len(opponents)} opponents...")
    
    seed = 42 # One deterministic seed for now
    
    results = {}
    all_wins = 0
    all_matches = 0
    
    for opp_path in opponents:
        opp_name = os.path.basename(opp_path)
        print(f"\n--- MATCH: chrisv99 vs {opp_name} ---")
        
        try:
            opp_agent = load_agent(opp_path)
        except Exception as e:
            print(f"Failed to load {opp_name}: {e}")
            continue
            
        # P0 match
        print(f"  [P0: chrisv99, P1: {opp_name}]")
        r0 = run_match(
            [make_runner(chris_agent), make_runner(opp_agent)],
            seed=seed
        )
        winner0 = r0['info'].get('winner')
        
        # P1 match
        print(f"  [P0: {opp_name}, P1: chrisv99]")
        r1 = run_match(
            [make_runner(opp_agent), make_runner(chris_agent)],
            seed=seed
        )
        winner1 = r1['info'].get('winner')
        
        # Count wins
        wins = 0
        if winner0 == 0: wins += 1
        if winner1 == 1: wins += 1
        
        results[opp_name] = wins
        all_wins += wins
        all_matches += 2
        
        print(f"  Result: {wins}/2 wins against {opp_name}")
        
    print("\n================ TOURNAMENT RESULTS ================")
    for opp, w in results.items():
        print(f"{opp}: {w}/2 wins")
    
    print(f"\nOVERALL WIN RATE: {all_wins}/{all_matches} ({(all_wins/all_matches)*100:.1f}%)")

if __name__ == "__main__":
    run_tournament()
