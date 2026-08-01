import sys, json, time
sys.path.insert(0, 'services/worker/engine/nexus_wars')
from run_match import make_runner, run_match, serialize_observation
sys.path.insert(0, 'test-bots/personal_agent')
import chris as chris_module

# Run a match with verbose observation logging
obs_log = []
action_log = []

def verbose_chris(obs):
    if isinstance(obs, dict):
        o = obs
    else:
        o = serialize_observation(obs)
    actions = chris_module.act(o)
    if actions:
        step = o.get("step", "?")
        n_my = len([p for p in o.get("planets", []) if p[1] == o.get("player", 0)])
        action_log.append(f"  step {step}: my_planets={n_my}, actions={actions[:3]}{'...' if len(actions)>3 else ''}")
    return actions

# Test vs random
from nexus_wars import agents
def random_agent(obs):
    # Use the engine's random agent
    from nexus_wars import agents as ag
    return ag.random(obs)

r = run_match([make_runner(verbose_chris), make_runner(ba_agent := __import__("benchmark_agents").agent_random)], seed=42)
print(f"vs Random: winner={r['info']['winner']}, scores={r['info']['scores']}")
print(f"Steps with actions: {len(action_log)}/500")
for line in action_log[:30]:
    print(line)
print(f"... ({len(action_log)} total action steps)")

# Also check if the agent is making ANY moves early
action_log.clear()
r = run_match([make_runner(verbose_chris), make_runner(ba_agent := __import__("benchmark_agents").agent_random)], seed=999)
print(f"\nvs Random (seed 999): winner={r['info']['winner']}, scores={r['info']['scores']}")
print(f"Steps with actions: {len(action_log)}/500")
for line in action_log[:30]:
    print(line)
