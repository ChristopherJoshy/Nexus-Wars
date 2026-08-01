import sys, json, math, random
sys.path.insert(0, 'services/worker/engine/nexus_wars')
sys.path.insert(0, 'test-bots/personal_agent')
import chris as chris_module

# Create a mock observation with a proper starting state
# Based on the engine's format: planets = [id, owner, x, y, radius, ships, production, energy, energyCap, energyRegen]
random.seed(42)

# Start with 2 players, ~8 planets each
planets = []
pid = 0
for i in range(4):  # 4 planets per player
    angle = i * math.pi / 2 + 0.1
    r = 15 + i * 5
    x = 50 + r * math.cos(angle)
    y = 50 + r * math.sin(angle)
    planets.append([pid, 0, x, y, 3.0, 50 + i*10, 3, 80, 100, 5])
    pid += 1

for i in range(4):  # 4 enemy planets
    angle = i * math.pi / 2 + math.pi + 0.1
    r = 15 + i * 5
    x = 50 + r * math.cos(angle)
    y = 50 + r * math.sin(angle)
    planets.append([pid, 1, x, y, 3.0, 50 + i*10, 3, 80, 100, 5])
    pid += 1

# Add some neutral planets
for i in range(8):
    angle = (i * math.pi / 4) + 0.3
    r = 30 + i * 2
    x = 50 + r * math.cos(angle)
    y = 50 + r * math.sin(angle)
    if 20 < r < 45:  # inner planets
        planets.append([pid, -1, x, y, 2.0, 5 + i*3, 2, 0, 100, 5])
        pid += 1

obs = {
    "planets": planets,
    "fleets": [],
    "player": 0,
    "angular_velocity": 0.035,
    "initial_planets": planets[:],  # copy
    "step": 0,
}

print("=== Planet summary ===")
for p in planets:
    print(f"  id={p[0]}, owner={p[1]}, x={p[2]:.1f}, y={p[3]:.1f}, ships={p[5]}, prod={p[6]}, energy={p[7]}")

my_planets = [p for p in planets if p[1] == 0]
target_planets = [p for p in planets if p[1] != 0]
print(f"\nMy planets: {len(my_planets)}")
print(f"Target planets: {len(target_planets)}")

# Create initial_map
initial_map = {p[0]: p for p in planets}

# Test scoring for first source and first target
src = my_planets[0]
tgt = target_planets[0]
print(f"\nTest scoring: src_id={src[0]}, tgt_id={tgt[0]}")

# Check if we can call _score_target
feats = [0.1]*10
import numpy as np
nn_val = chris_module._nn_score(np.array(feats, dtype=np.float32))
print(f"NN test score: {nn_val}")

# Check _orbital_pos
pred = chris_module._orbital_pos(tgt[0], initial_map, (tgt[2], tgt[3]), 5, 0.035)
print(f"Predicted position: {pred}")

# Check _path_hits_sun
hits = chris_module._path_hits_sun(src[2], src[3], tgt[2], tgt[3])
print(f"Path hits sun: {hits}")

# Check full act
actions = chris_module.act(obs)
print(f"\nActions returned: {actions}")
print(f"Number of actions: {len(actions)}")

# Debug: check ships_needed and available
print(f"\n=== Debug scoring ===")
for t in target_planets[:3]:
    src_ships = src[5]
    send_est = min(src_ships, 60)
    speed_est = chris_module._fleet_speed(max(send_est, 5))
    raw_dist = chris_module._dist(src[2], src[3], t[2], t[3])
    eta = max(1, int(math.ceil(raw_dist / speed_est))) if speed_est > 0 else 999
    ships_needed = int(t[5]) + int(t[6]) * eta + (3 if t[1] != -1 else -int(t[5]) + 1)
    if t[1] == -1:
        ships_needed = int(t[5]) + 1
    print(f"  tgt={t[0]}, ships={t[5]}, prod={t[6]}, dist={raw_dist:.1f}, eta={eta}, needed={ships_needed}, src_ships={src_ships}")

# More detailed scoring
for t in target_planets[:3]:
    result = chris_module._score_target(
        src, t, 0, 0.035, initial_map, [], planet_by_id := {p[0]: p for p in planets}, 0, False, set(), {}, 0.0
    )
    print(f"  score_result: {result}")
