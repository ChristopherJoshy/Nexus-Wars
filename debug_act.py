import sys, json, math
sys.path.insert(0, 'services/worker/engine/nexus_wars')
sys.path.insert(0, 'test-bots/personal_agent')
import chris as chris_module
import nexus_wars

# Get a real observation
from nexus_wars import state_utils
env = nexus_wars.NexusWars()
obs = env.reset(seed=42)

# obs might be a namedtuple, serialize it
from run_match import serialize_observation
obs_dict = serialize_observation(obs) if not isinstance(obs, dict) else obs

print("=== Observation ===")
print(f"player: {obs_dict.get('player')}")
print(f"step: {obs_dict.get('step')}")
print(f"num planets: {len(obs_dict.get('planets', []))}")
print(f"num fleets: {len(obs_dict.get('fleets', []))}")
print(f"angular_velocity: {obs_dict.get('angular_velocity')}")
print(f"num initial_planets: {len(obs_dict.get('initial_planets', []))}")

# Print our planets
me = obs_dict.get('player', 0)
for p in obs_dict.get('planets', []):
    if p[1] == me:
        print(f"  My planet: id={p[0]}, owner={p[1]}, x={p[2]}, y={p[3]}, r={p[4]}, ships={p[5]}, prod={p[6]}, energy={p[7] if len(p)>7 else '?'}")

# Print target planets
for p in obs_dict.get('planets', []):
    if p[1] != me:
        print(f"  Target: id={p[0]}, owner={p[1]}, ships={p[5]}, prod={p[6]}")

# Now call act directly
try:
    actions = chris_module.act(obs_dict)
    print(f"\n=== Actions returned: {actions}")
    print(f"Number of actions: {len(actions)}")
except Exception as e:
    import traceback
    print(f"\n=== Exception: {e}")
    traceback.print_exc()

# Try step by step debugging
print("\n=== Step-by-step debugging ===")
player = int(obs_dict.get("player", 0))
planets_raw = obs_dict.get("planets", [])
step = int(obs_dict.get("step", 0))
angular_vel = float(obs_dict.get("angular_velocity", 0.035))
initial_raw = obs_dict.get("initial_planets", [])

planet_by_id = {}
for p in planets_raw:
    if isinstance(p, (list, tuple)) and len(p) >= 7:
        planet_by_id[p[0]] = p

initial_map = {}
for p in initial_raw:
    if isinstance(p, (list, tuple)) and len(p) >= 7:
        initial_map[p[0]] = p

my_planets = [p for p in planets_raw if isinstance(p, (list, tuple)) and len(p) >= 7 and int(p[1]) == player]
enemy_planets = [p for p in planets_raw if isinstance(p, (list, tuple)) and len(p) >= 7 and int(p[1]) != player and int(p[1]) != -1]
neutral_planets = [p for p in planets_raw if isinstance(p, (list, tuple)) and len(p) >= 7 and int(p[1]) == -1]
target_planets = enemy_planets + neutral_planets

print(f"my_planets: {len(my_planets)}")
print(f"enemy_planets: {len(enemy_planets)}")
print(f"neutral_planets: {len(neutral_planets)}")
print(f"target_planets: {len(target_planets)}")

if my_planets:
    src = my_planets[0]
    print(f"\nSource planet: id={src[0]}, ships={src[5]}, prod={src[6]}, energy={src[7] if len(src)>7 else '?'}")
    
    if target_planets:
        tgt = target_planets[0]
        print(f"Target planet: id={tgt[0]}, owner={tgt[1]}, ships={tgt[5]}, prod={tgt[6]}")
        
        # Test scoring
        fleets_raw = obs_dict.get("fleets", [])
        enemy_fleets = [f for f in fleets_raw if isinstance(f, (list, tuple)) and len(f) >= 8 and int(f[1]) != player and int(f[6]) > 0]
        my_fleets = [f for f in fleets_raw if isinstance(f, (list, tuple)) and len(f) >= 8 and int(f[1]) == player and int(f[6]) > 0]
        
        result = chris_module._score_target(
            src, tgt, step, angular_vel, initial_map, my_fleets,
            planet_by_id, player, False, set(), {}, rot_angle=0.0
        )
        print(f"\nTarget score result: {result}")
    else:
        print("No target planets!")
