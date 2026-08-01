import sys, time
sys.path.insert(0, 'services/worker/engine/nexus_wars')
sys.path.insert(0, '.')
sys.path.insert(0, 'test-bots/personal_agent')
import chris
from run_match import run_match, InProcessRunner
import benchmark_agents as ba

def chris_agent(obs):
    return chris.agent_fn(obs)

for name, opp in [('random', ba.agent_random), ('fortress', ba.agent_fortress), ('viper', ba.agent_viper), ('chimera', ba.agent_chimera), ('chimera-np', ba.agent_chimera_np)]:
    t0 = time.time()
    try:
        r = run_match([InProcessRunner(chris_agent), InProcessRunner(opp)], seed=42)
        t1 = time.time()
        print(f'{name}: {t1-t0:.3f}s, winner: {r["info"]["winner"]}')
    except Exception as e:
        t1 = time.time()
        print(f'{name}: {t1-t0:.3f}s, ERROR: {e}')
