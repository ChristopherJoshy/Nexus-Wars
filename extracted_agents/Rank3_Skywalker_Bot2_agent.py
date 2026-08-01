import sys
import json
import math

# --- Game Constants ---
SUN_POS = (50.0, 50.0)
SUN_RADIUS = 10.0
LAUNCH_ENERGY_COST = 20

def get_fleet_speed(ships):
    if ships <= 1: return 1.0
    return min(6.0, 1.0 + 5.0 * ((math.log(ships) / math.log(1000.0)) ** 1.5))

def predict_intercept(src_x, src_y, t_x, t_y, t_radius, angular_velocity, fleet_speed):
    sun_dist = math.hypot(t_x - SUN_POS[0], t_y - SUN_POS[1])
    if sun_dist + t_radius >= 50.0:
        dist = math.hypot(t_x - src_x, t_y - src_y)
        return math.atan2(t_y - src_y, t_x - src_x), t_x, t_y, dist / fleet_speed
        
    r = sun_dist
    current_theta = math.atan2(t_y - SUN_POS[1], t_x - SUN_POS[0])
    for t in range(1, 150):
        theta_t = current_theta + angular_velocity * t
        hx = SUN_POS[0] + r * math.cos(theta_t)
        hy = SUN_POS[1] + r * math.sin(theta_t)
        if math.hypot(hx - src_x, hy - src_y) / fleet_speed <= t:
            low = max(0.0, t - 1.0)
            high = float(t)
            for _ in range(15):
                mid = (low + high) / 2.0
                theta_mid = current_theta + angular_velocity * mid
                mx = SUN_POS[0] + r * math.cos(theta_mid)
                my = SUN_POS[1] + r * math.sin(theta_mid)
                req_mid = math.hypot(mx - src_x, my - src_y) / fleet_speed
                if req_mid <= mid:
                    high = mid
                else:
                    low = mid
            
            theta_exact = current_theta + angular_velocity * high
            ex = SUN_POS[0] + r * math.cos(theta_exact)
            ey = SUN_POS[1] + r * math.sin(theta_exact)
            return math.atan2(ey - src_y, ex - src_x), ex, ey, high
            
    return math.atan2(t_y - src_y, t_x - src_x), t_x, t_y, 1000

def passes_through_sun(src_x, src_y, hx, hy):
    px, py = SUN_POS
    dx, dy = hx - src_x, hy - src_y
    len_sq = dx*dx + dy*dy
    if len_sq == 0: return math.hypot(src_x - px, src_y - py) <= SUN_RADIUS
    t = max(0.0, min(1.0, ((px - src_x) * dx + (py - src_y) * dy) / len_sq))
    return math.hypot((src_x + t * dx) - px, (src_y + t * dy) - py) <= SUN_RADIUS

def calculate_threats(my_planets, enemy_fleets, angular_velocity):
    threats = {p[0]: 0 for p in my_planets}
    for f in enemy_fleets:
        fx, fy, fangle, fships = f[2], f[3], f[4], f[6]
        fspeed = get_fleet_speed(fships)
        
        best_hit_t = 999
        hit_p = None
        
        for p in my_planets:
            p_id, px, py, pradius = p[0], p[2], p[3], p[4]
            sun_dist = math.hypot(px - SUN_POS[0], py - SUN_POS[1])
            is_orbiting = (sun_dist + pradius < 50.0)
            
            # fast check: moving away?
            dx = px - fx
            dy = py - fy
            if math.cos(fangle) * dx + math.sin(fangle) * dy < 0:
                continue
                
            for t in range(1, 150):
                curr_fx = fx + math.cos(fangle) * fspeed * t
                curr_fy = fy + math.sin(fangle) * fspeed * t
                
                if is_orbiting:
                    theta = math.atan2(py - SUN_POS[1], px - SUN_POS[0]) + angular_velocity * t
                    curr_px = SUN_POS[0] + sun_dist * math.cos(theta)
                    curr_py = SUN_POS[1] + sun_dist * math.sin(theta)
                else:
                    curr_px, curr_py = px, py
                    
                if math.hypot(curr_fx - curr_px, curr_fy - curr_py) <= pradius:
                    if t < best_hit_t:
                        best_hit_t = t
                        hit_p = p_id
                    break
                    
        if hit_p is not None:
            threats[hit_p] += fships
            
    return threats

def act(observation):
    player_id = observation.get("player", 0)
    angular_velocity = observation.get("angular_velocity", 0.035)
    planets = observation.get("planets", [])
    fleets = observation.get("fleets", [])
    
    my_planets = [p for p in planets if p[1] == player_id]
    other_planets = [p for p in planets if p[1] != player_id]
    enemy_fleets = [f for f in fleets if f[1] != player_id]
    commands = []
    
    threats = calculate_threats(my_planets, enemy_fleets, angular_velocity)
    
    for source in my_planets:
        p_id, owner, x, y, radius, ships, prod, energy, cap, regen = source
        
        # Base engine rules: Can't launch without energy or ships
        if energy < LAUNCH_ENERGY_COST or ships == 0:
            continue
            
        incoming_threat = threats.get(p_id, 0)
        keep_ships = int(incoming_threat * 1.1) if incoming_threat > 0 else 0
        available_ships = ships - keep_ships
        
        # Removed artificial 15-ship hoarding rule to allow micro-fleet expansion
            
        # 1. Multi-Launch Offensive Phase
        scored_targets = []
        for target in other_planets:
            t_id, t_owner, tx, ty, t_radius, t_ships, t_prod, t_energy, _, _ = target
            dist = math.hypot(tx - x, ty - y)
            
            if t_owner == -1:
                base_needed = int(t_ships + 1)
                priority = 10000.0  
            else:
                base_needed = t_ships
                for _ in range(3):
                    spd = get_fleet_speed(base_needed)
                    steps = dist / max(0.1, spd)
                    base_needed = t_ships + (t_prod * steps)
                base_needed = int(base_needed * 1.1) + 1
                priority = 1.0

            if available_ships >= base_needed and energy >= LAUNCH_ENERGY_COST:
                est_send = max(base_needed, int(available_ships * 0.5))
                fleet_speed = get_fleet_speed(est_send)
                angle, hx, hy, travel_steps = predict_intercept(
                    x, y, tx, ty, t_radius, angular_velocity, fleet_speed
                )
                
                if not passes_through_sun(x, y, hx, hy):
                    score = ((t_prod ** 2) * priority) / (travel_steps + 1.0)
                    scored_targets.append((score, base_needed, angle))

        scored_targets.sort(key=lambda item: item[0], reverse=True)
        
        launched_this_turn = False
        for score, base_needed, angle in scored_targets:
            if available_ships >= base_needed and energy >= LAUNCH_ENERGY_COST:
                ships_to_send = max(base_needed, int(available_ships * 0.5))
                commands.append([p_id, angle, ships_to_send])
                available_ships -= ships_to_send
                energy -= LAUNCH_ENERGY_COST
                launched_this_turn = True
            
            if energy < LAUNCH_ENERGY_COST:
                break

        # 2. Desperation / Consolidation Phase (Energy Dump)
        if not launched_this_turn and energy >= 80 and len(my_planets) > 1 and available_ships > 5:
            closest_ally, closest_dist = None, float('inf')
            best_launch_angle = 0.0
            for ally in my_planets:
                if ally[0] == p_id: continue
                dist = math.hypot(ally[2] - x, ally[3] - y)
                if dist < closest_dist:
                    angle, hx, hy, _ = predict_intercept(
                        x, y, ally[2], ally[3], ally[4], angular_velocity, get_fleet_speed(available_ships)
                    )
                    if not passes_through_sun(x, y, hx, hy):
                        closest_dist = dist
                        closest_ally = ally
                        best_launch_angle = angle

            if closest_ally:
                commands.append([p_id, best_launch_angle, int(available_ships)])
                available_ships -= int(available_ships)
                energy -= LAUNCH_ENERGY_COST
            
    return commands

if __name__ == "__main__":
    for line in sys.stdin:
        if not line.strip(): continue
        try:
            obs = json.loads(line)
            sys.stdout.write(json.dumps(act(obs)) + "\n")
            sys.stdout.flush()
        except Exception as e:
            print(f"[ERROR] Engine loop crash: {e}", file=sys.stderr)
            sys.stderr.flush()