import sys, time
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match
sys.path.insert(0, 'test-bots/personal_agent')
import chris as chris_module
import benchmark_agents as ba

print('agent_fn:', hasattr(chris_module, 'agent_fn'))
print('agent:', hasattr(chris_module, 'agent'))

# Test vs random first
t0 = time.time()
r = run_match([make_runner(chris_module.agent), make_runner(ba.agent_random)], seed=42)
dt = time.time() - t0
print(f'Random (P0): winner={r["info"]["winner"]}, duration={dt:.2f}s')

t0 = time.time()
r = run_match([make_runner(ba.agent_random), make_runner(chris_module.agent)], seed=42)
dt = time.time() - t0
print(f'Random (P1): winner={r["info"]["winner"]}, duration={dt:.2f}s')
print(f'Match info: {r["info"]}')

# Test vs fortress
t0 = time.time()
r = run_match([make_runner(chris_module.agent), make_runner(ba.agent_fortress)], seed=42)
dt = time.time() - t0
print(f'Fortress (P0): winner={r["info"]["winner"]}, duration={dt:.2f}s')

t0 = time.time()
r = run_match([make_runner(ba.agent_fortress), make_runner(chris_module.agent)], seed=42)
dt = time.time() - t0
print(f'Fortress (P1): winner={r["info"]["winner"]}, duration={dt:.2f}s')

# Test vs chimera
t0 = time.time()
r = run_match([make_runner(chris_module.agent), make_runner(ba.agent_chimera)], seed=42)
dt = time.time() - t0
print(f'Chimera (P0): winner={r["info"]["winner"]}, duration={dt:.2f}s')

# Test vs chimera-np
t0 = time.time()
r = run_match([make_runner(chris_module.agent), make_runner(ba.agent_chimera_np)], seed=42)
dt = time.time() - t0
print(f'Chimera-np (P0): winner={r["info"]["winner"]}, duration={dt:.2f}s')

# Test vs viper
t0 = time.time()
r = run_match([make_runner(chris_module.agent), make_runner(ba.agent_viper)], seed=42)
dt = time.time() - t0
print(f'Viper (P0): winner={r["info"]["winner"]}, duration={dt:.2f}s')

print("\n--- Testing Downloads bots ---")
sys.path.insert(0, 'C:/Users/chris/Downloads')
downloads_agent = __import__('agent')
downloads_agent2 = __import__('agent (1)')

def dl_agent1(obs):
    import io
    old_out = sys.stdout
    old_in = sys.stdin
    buf = io.StringIO()
    sys.stdout = buf
    sys.stdin = io.StringIO(json.dumps(obs) + '\n')
    try:
        downloads_agent.main()
    except:
        pass
    sys.stdout = old_out
    sys.stdin = old_in
    out = buf.getvalue().strip()
    if not out: return []
    try:
        return json.loads(out.splitlines()[-1])
    except:
        return []

def dl_agent2(obs):
    import io
    old_out = sys.stdout
    old_in = sys.stdin
    buf = io.StringIO()
    sys.stdout = buf
    sys.stdin = io.StringIO(json.dumps(obs) + '\n')
    try:
        downloads_agent2.main()
    except:
        pass
    sys.stdout = old_out
    sys.stdin = old_in
    out = buf.getvalue().strip()
    if not out: return []
    try:
        return json.loads(out.splitlines()[-1])
    except:
        return []

t0 = time.time()
r = run_match([make_runner(chris_module.agent), make_runner(dl_agent1)], seed=42)
dt = time.time() - t0
print(f'Downloads agent.py (P0): winner={r["info"]["winner"]}, duration={dt:.2f}s')

t0 = time.time()
r = run_match([make_runner(chris_module.agent), make_runner(dl_agent2)], seed=42)
dt = time.time() - t0
print(f'Downloads agent(1).py (P0): winner={r["info"]["winner"]}, duration={dt:.2f}s')
