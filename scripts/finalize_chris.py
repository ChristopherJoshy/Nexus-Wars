#!/usr/bin/env python3
"""Generate the final single-file chris.py with NES-optimized evaluator weights.

Replaces the older bake.py. Embeds the full v7 heuristic code directly as a
string constant (avoiding fragile extraction-from-current-file), with the
NES-trained neural evaluator weights (W1/B1/W2/B2) inlined as Python lists.

The agent drops the macro-action RL policy (proven ineffective ~50% win rate
vs all opponents) and runs the v7 heuristic with NES-optimized evaluator
weights directly.
"""

import json
import os
import textwrap

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ES_WEIGHTS_PATH = os.path.join(REPO_ROOT, 'test-bots', 'personal_agent', '_es_evaluator_b64.txt')
OUT_PATH = os.path.join(REPO_ROOT, 'test-bots', 'personal_agent', 'chris.py')

# Fallback to v7 hand-tuned weights if no ES weights found
FALLBACK_W1 = [
    [-12.0,  0.0,  6.20, -0.50, -3.50,  3.50, -0.80,  0.10,  0.50,  0.50],
    [-11.5,  0.0,  5.50, -0.20, -3.10,  3.10, -0.50,  0.05,  0.40,  0.40],
    [-12.8,  0.0,  6.80, -0.80, -4.20,  2.80, -1.20,  0.20,  0.60,  0.60],
    [-10.5,  0.0,  5.10, -0.30, -3.20,  3.80, -0.40,  0.15,  0.30,  0.30],
    [-14.0,  0.0,  4.80, -0.40, -2.80,  4.50, -1.50, -0.20,  0.40,  0.40],
    [-13.2,  0.0,  4.20, -0.30, -2.50,  4.10, -1.20, -0.15,  0.30,  0.30],
    [-13.8,  0.0,  5.10, -0.50, -3.10,  4.80, -1.80, -0.25,  0.50,  0.50],
    [-10.0,  0.0,  5.50, -0.80, -3.80, -0.50,  3.80,  0.80,  0.60,  0.80],
    [-11.2,  0.0,  6.10, -1.10, -4.20, -0.80,  4.20,  0.90,  0.70,  0.90],
    [-10.8,  0.0,  4.90, -0.60, -3.20, -0.30,  3.20,  0.70,  0.50,  0.70],
    [-12.1,  0.0,  5.20, -0.40, -3.20,  2.50,  1.80,  0.30,  0.40,  0.50],
    [-11.8,  0.0,  4.80, -0.50, -2.80,  2.80,  1.50,  0.20,  0.50,  0.60],
    [-12.4,  0.0,  5.60, -0.30, -3.60,  2.20,  2.10,  0.40,  0.30,  0.40],
    [-12.5,  0.0,  4.50, -0.60, -2.50,  3.20,  1.20,  0.10,  0.60,  0.70],
    [-11.9,  0.0,  5.90, -0.20, -3.90,  2.00,  2.40,  0.50,  0.20,  0.30],
    [-13.0,  0.0,  4.10, -0.70, -2.10,  3.50,  0.90,  0.00,  0.70,  0.80],
]
FALLBACK_B1 = [0.5, 0.4, 0.6, 0.5, 0.8, 0.7, 0.9, 0.3, 0.4, 0.2, 0.5, 0.6, 0.4, 0.7, 0.3, 0.8]
FALLBACK_W2 = [[2.5], [2.2], [2.8], [2.4], [2.0], [1.6], [2.2],
               [1.5], [1.7], [1.3], [1.4], [1.5], [1.6], [1.4], [1.5], [1.4]]
FALLBACK_B2 = [1.0]


def format_weights(w1, b1, w2, b2):
    """Format weights as Python list literals for embedding."""
    def fmt_list(lst, indent, precision=6):
        parts = []
        for v in lst:
            parts.append(f"{round(float(v), precision):.6f}")
        return ", ".join(parts)

    def fmt_matrix(mat, indent, precision=6):
        rows = []
        for row in mat:
            rows.append(indent + "    [" + fmt_list(row, indent, precision) + "]")
        return ",\n".join(rows)

    w1_str = fmt_matrix(w1, "    ")
    b1_str = "    [" + fmt_list(b1, "    ") + "]"
    w2_str = fmt_matrix(w2, "    ")
    b2_str = "    [" + fmt_list(b2, "    ") + "]"

    return w1_str, b1_str, w2_str, b2_str


HEURISTIC_CODE = r'''
import json
import math
import sys

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ── Constants ──
BOARD_SIZE   = 100.0
CENTER       = 50.0
SUN_DANGER   = 12.0
MAX_SPEED    = 6.0
MIN_SPEED    = 1.0
LAUNCH_COST  = 20
MIN_LAUNCH   = 5
ROTATION_LIM = 50.0
MAX_PREDICT  = 60

ENERGY_GATE         = 40
URGENT_DEFENCE_ETA  = 20
EARLY_EXPAND_STEP   = 40
COORD_STRIKE_DIST   = 35.0
COORD_MIN_SOURCES   = 2

# ── Neural Evaluator weights (NES-optimized) ──
W1 = [W1_VALUES]
B1 = [B1_VALUES]
W2 = [W2_VALUES]
B2 = [B2_VALUES]


def _forward_pure(features):
    hidden = [max(0.0, sum(features[j] * W1[i][j] for j in range(len(features))) + B1[i])
              for i in range(16)]
    return sum(hidden[i] * W2[i][0] for i in range(16)) + B2[0]


def _forward_numpy(features):
    x = np.array(features, dtype=np.float32)
    h = np.maximum(0.0, x @ np.array(W1, dtype=np.float32).T + np.array(B1, dtype=np.float32))
    return float((h @ np.array(W2, dtype=np.float32) + np.array(B2, dtype=np.float32)).item())


def _neural_eval(features):
    if HAS_NUMPY:
        try:
            return _forward_numpy(features)
        except Exception:
            pass
    return _forward_pure(features)


def _fleet_speed(ships):
    if ships <= 0:
        return 0.0
    return min(MAX_SPEED, MIN_SPEED + (MAX_SPEED - MIN_SPEED) *
               (math.log(max(ships, 1)) / math.log(1000)) ** 1.5)


def _vdist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def _path_hits_sun(x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0.0 and dy == 0.0:
        return False
    fx, fy = x1 - CENTER, y1 - CENTER
    a = dx * dx + dy * dy
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - SUN_DANGER * SUN_DANGER
    disc = b * b - 4.0 * a * c
    if disc <= 0.0:
        return False
    sq = math.sqrt(disc)
    t1 = (-b - sq) / (2.0 * a)
    t2 = (-b + sq) / (2.0 * a)
    return (0.0 < t1 < 1.0) or (0.0 < t2 < 1.0) or (t1 <= 0.0 <= t2)


def _safe_angle(sx, sy, tx, ty):
    direct = math.atan2(ty - sy, tx - sx)
    if not _path_hits_sun(sx, sy, tx, ty):
        return direct
    vx, vy = CENTER - sx, CENTER - sy
    d = math.hypot(vx, vy)
    if d <= SUN_DANGER + 0.1:
        return direct
    base = math.atan2(vy, vx)
    half = math.asin(min(1.0, SUN_DANGER / d))
    t1, t2 = base + half, base - half
    ta = math.atan2(ty - sy, tx - sx)
    d1 = abs((t1 - ta + math.pi) % (2.0 * math.pi) - math.pi)
    d2 = abs((t2 - ta + math.pi) % (2.0 * math.pi) - math.pi)
    return t1 if d1 <= d2 else t2


def _orbital_pos(ip_x, ip_y, radius, step, av):
    dx, dy = ip_x - CENTER, ip_y - CENTER
    r = math.hypot(dx, dy)
    if r + radius >= ROTATION_LIM:
        return ip_x, ip_y
    base = math.atan2(dy, dx)
    return CENTER + r * math.cos(base + av * step), CENTER + r * math.sin(base + av * step)


def _predict_pos(planet, target_step, av, initial_map):
    ip = initial_map.get(planet[0])
    if ip is not None:
        return _orbital_pos(ip[2], ip[3], planet[4], target_step, av)
    return planet[2], planet[3]


def _est_arrival(sx, sy, planet, ships, step, av, initial_map):
    spd = _fleet_speed(ships)
    raw = _vdist(sx, sy, planet[2], planet[3])
    rg = min(MAX_PREDICT, raw / max(spd, 0.1))
    tx, ty = _predict_pos(planet, step + rg, av, initial_map)
    d = max(1.0, _vdist(sx, sy, tx, ty))
    fine = min(MAX_PREDICT, d / max(spd, 0.1))
    tx2, ty2 = _predict_pos(planet, step + fine, av, initial_map)
    return fine, tx2, ty2


def _fleet_target(fleet, planets):
    fx, fy = fleet[2], fleet[3]
    dx, dy = math.cos(fleet[4]), math.sin(fleet[4])
    best_id, min_ld = None, 999.0
    for p in planets:
        vx = p[2] - fx
        vy = p[3] - fy
        if vx * dx + vy * dy <= 0.0:
            continue
        ld = abs(vx * dy - vy * dx)
        if ld <= (p[4] + 5.0) and ld < min_ld:
            min_ld = ld
            best_id = p[0]
    if best_id is None:
        return None, 0.0
    tp = next(p for p in planets if p[0] == best_id)
    return best_id, _vdist(fx, fy, tp[2], tp[3])


def _neutral_secured(target_id, friendly_in, current_ships):
    return friendly_in.get(target_id, 0) >= current_ships.get(target_id, 0)


def _closest_capturable_neutral(src, neutrals, available, step, av, initial_map):
    if not neutrals:
        return None
    sx, sy = _predict_pos(src, step, av, initial_map)
    best, best_score = None, 1e18
    for p in neutrals:
        eta, _, _ = _est_arrival(sx, sy, p, available, step, av, initial_map)
        need = p[5] + 5
        if available < need:
            continue
        score = eta * 10 + p[5] * 0.1
        if score < best_score:
            best_score = score
            best = (p, eta)
    return best


def _rollout(planets, me, friendly_in, threat_in, horizon=20):
    proj = {}
    for p in planets:
        base = p[5]
        if p[1] == me:
            base += horizon * p[6] + friendly_in[p[0]] - threat_in[p[0]]
        elif p[1] >= 0:
            base -= threat_in[p[0]]
        else:
            base += friendly_in[p[0]] - threat_in[p[0]]
        proj[p[0]] = max(0, base)
    return proj


def _calc_send(planet, available, eta):
    garrison = planet[5]
    prod = planet[6]
    if planet[1] < 0:
        needed = garrison + 3
        return max(MIN_LAUNCH, min(available, needed))
    arrival = int(garrison + prod * eta * 0.5)
    needed = arrival + 5
    if needed > available:
        return 0
    return min(available, min(int(available * 0.70), max(needed, MIN_LAUNCH)))


def _extract_features(src, target, fut_x, fut_y, proj_ships, step, me):
    d_fut = _vdist(src[2], src[3], fut_x, fut_y)
    norm_dist = d_fut / 141.42
    is_static = 0.0
    norm_prod = target[6] / 10.0
    norm_sh = min(target[5] / 100.0, 1.0)
    proj20 = proj_ships.get(target[0], target[5])
    norm_p20 = min(proj20 / 100.0, 1.0)
    is_neut = 1.0 if target[1] < 0 else 0.0
    is_enemy = 1.0 if (target[1] >= 0 and target[1] != me) else 0.0
    norm_step = step / 500.0
    norm_enrg = src[7] / 100.0
    norm_srcs = min(src[5] / 100.0, 1.0)
    return [norm_dist, is_static, norm_prod, norm_sh, norm_p20,
            is_neut, is_enemy, norm_step, norm_enrg, norm_srcs]


def _run_heuristic(obs):
    me = int(obs.get("player", 0))
    step = int(obs.get("step", 0))
    av = float(obs.get("angular_velocity", 0.035))
    planets = obs.get("planets", [])
    fleets = obs.get("fleets", [])
    initial_map = {ip[0]: ip for ip in obs.get("initial_planets", [])}

    my_planets = [p for p in planets if p[1] == me]
    non_my = [p for p in planets if p[1] != me]
    enemy_pl = [p for p in planets if p[1] >= 0 and p[1] != me]
    neutrals = [p for p in non_my if p[1] < 0]
    if not my_planets or not non_my:
        return []

    threat_sh = {p[0]: 0 for p in planets}
    threat_eta = {p[0]: 999.0 for p in planets}
    friendly = {p[0]: 0 for p in planets}
    for f in fleets:
        tid, dist = _fleet_target(f, planets)
        if tid is None or dist <= 0.0:
            continue
        spd = _fleet_speed(f[6])
        eta = dist / spd if spd > 0.0 else 999.0
        if f[1] == me:
            friendly[tid] += f[6]
        else:
            threat_sh[tid] += f[6]
            if eta < threat_eta[tid]:
                threat_eta[tid] = eta

    proj_ships = _rollout(planets, me, friendly, threat_sh)
    current_ships = {p[0]: p[5] for p in planets}

    my_planets.sort(key=lambda p: p[5], reverse=True)
    actions = []

    def _launch(src, target, n, step, av, initial_map):
        sx, sy = _predict_pos(src, step, av, initial_map)
        _, fx, fy = _est_arrival(sx, sy, target, n, step, av, initial_map)
        ang = _safe_angle(sx, sy, fx, fy)
        actions.append([src[0], ang, int(n)])
        src[5] -= n
        src[7] = max(0, src[7] - LAUNCH_COST)
        friendly[target[0]] += n

    for src in my_planets:
        sid = src[0]
        ships = src[5]
        energy = src[7]
        prod = src[6]

        if energy < ENERGY_GATE:
            continue
        if ships < MIN_LAUNCH:
            continue

        sx, sy = _predict_pos(src, step, av, initial_map)
        ts = threat_sh.get(sid, 0)
        te = threat_eta.get(sid, 999.0)
        min_keep = max(MIN_LAUNCH, int(ts * 0.65) + prod * 2 if (ts > 0 and te < 35)
                       else prod * 2 + 2)
        available = ships - min_keep
        if available < MIN_LAUNCH:
            continue

        if step < EARLY_EXPAND_STEP and len(my_planets) < 4:
            greedy = _closest_capturable_neutral(src, neutrals, available, step, av, initial_map)
            if greedy is not None:
                tgt, eta = greedy
                if not _neutral_secured(tgt[0], friendly, current_ships):
                    n = _calc_send(tgt, available, eta)
                    if n >= MIN_LAUNCH:
                        _launch(src, tgt, n, step, av, initial_map)
                        continue

        threatened = [p for p in my_planets
                      if p[0] != sid
                      and threat_sh.get(p[0], 0) > 0
                      and threat_eta.get(p[0], 999.0) < URGENT_DEFENCE_ETA
                      and threat_sh.get(p[0], 0) > p[5] * 0.6]
        if threatened:
            tgt = min(threatened, key=lambda p: _vdist(sx, sy, p[2], p[3]))
            gap = max(MIN_LAUNCH, threat_sh[tgt[0]] - tgt[5] - friendly.get(tgt[0], 0) + 5)
            def_n = max(MIN_LAUNCH, min(gap, available))
            if def_n >= MIN_LAUNCH:
                _launch(src, tgt, def_n, step, av, initial_map)
                continue

        snipe_done = False
        for f in fleets:
            if f[1] == me:
                continue
            tid, dist = _fleet_target(f, planets)
            if tid is None:
                continue
            tp = next((p for p in non_my if p[0] == tid and p[1] < 0), None)
            if tp is None:
                continue
            e_spd = _fleet_speed(f[6])
            e_eta = dist / e_spd if e_spd > 0.0 else 999.0
            payload = abs(f[6] - tp[5]) + 3
            if available < payload:
                continue
            my_eta, px, py = _est_arrival(sx, sy, tp, payload, step, av, initial_map)
            if 0.0 <= (my_eta - e_eta) <= 5.0:
                _launch(src, tp, payload, step, av, initial_map)
                snipe_done = True
                break
        if snipe_done:
            continue

        send_ships = available // 2 if available // 2 >= MIN_LAUNCH else MIN_LAUNCH
        best_score = -99999.0
        best_target = None
        best_eta_v = 0.0
        second_best = None
        second_score = -99999.0

        for target in non_my:
            if target[1] < 0 and _neutral_secured(target[0], friendly, current_ships):
                continue
            eta_t, tx, ty = _est_arrival(sx, sy, target, send_ships, step, av, initial_map)
            sc = _neural_eval(_extract_features(src, target, tx, ty, proj_ships, step, me))
            if sc > best_score:
                second_score = best_score
                second_best = best_target
                best_score = sc
                best_target = target
                best_eta_v = eta_t
            elif sc > second_score:
                second_score = sc
                second_best = target

        if best_target is not None:
            n = _calc_send(best_target, available, best_eta_v)
            if n >= MIN_LAUNCH and energy >= LAUNCH_COST:
                _launch(src, best_target, n, step, av, initial_map)
                if (step < EARLY_EXPAND_STEP
                        and available - n >= MIN_LAUNCH
                        and second_best is not None
                        and second_best[1] < 0):
                    eta2, _, _ = _est_arrival(sx, sy, second_best, available - n, step, av, initial_map)
                    n2 = _calc_send(second_best, available - n, eta2)
                    if n2 >= MIN_LAUNCH:
                        _launch(src, second_best, n2, step, av, initial_map)
                continue

        if best_target is None or best_target[1] >= 0:
            nearby_planets = [p for p in my_planets
                              if p[0] != sid and _vdist(p[2], p[3], src[2], src[3]) < COORD_STRIKE_DIST
                              and p[5] >= MIN_LAUNCH * 2 and p[7] >= LAUNCH_COST]
            if len(nearby_planets) + 1 >= COORD_MIN_SOURCES and enemy_pl:
                candidates = []
                for ep in enemy_pl:
                    if friendly.get(ep[0], 0) >= ep[5] * 1.5:
                        continue
                    est_force = ships
                    for partner in nearby_planets:
                        est_force += partner[5] * 0.6
                    need = ep[5] + ep[6] * 5 + 8
                    if est_force >= need:
                        _, px, py = _est_arrival(sx, sy, ep, ships, step, av, initial_map)
                        candidates.append((need, ep, px, py))
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    _, best_ep, btx, bty = candidates[0]
                    _launch(src, best_ep, ships, step, av, initial_map)
                    continue

        if len(my_planets) > 1 and enemy_pl:
            frontline = min(my_planets,
                            key=lambda p: min(_vdist(p[2], p[3], ep[2], ep[3]) for ep in enemy_pl))
            n = available // 3
            if sid != frontline[0] and n >= MIN_LAUNCH and energy >= LAUNCH_COST:
                _launch(src, frontline, n, step, av, initial_map)

    return actions
'''


ENTRYPOINT = r'''
# ═══ Agent entrypoint ═══
def agent_fn(obs):
    try:
        return _run_heuristic(obs)
    except Exception:
        return []


if __name__ == "__main__":
    for line in sys.stdin:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            obs = json.loads(line_str)
            sys.stdout.write(json.dumps(agent_fn(obs)) + "\n")
            sys.stdout.flush()
        except Exception:
            sys.stdout.write("[]\n")
            sys.stdout.flush()
'''


def main():
    # Load NES-trained evaluator weights
    w1, b1, w2, b2 = FALLBACK_W1, FALLBACK_B1, FALLBACK_W2, FALLBACK_B2

    es_path = os.path.join(REPO_ROOT, 'test-bots', 'personal_agent', '_es_evaluator_b64.txt')
    if os.path.exists(es_path):
        with open(es_path) as f:
            es_weights = json.loads(f.read())
        w1 = es_weights["W1"]
        b1 = es_weights["B1"]
        w2 = es_weights["W2"]
        b2 = es_weights["B2"]
        print(f"Loaded NES-optimized evaluator weights from {es_path}")
    else:
        print("No ES weights found, using v7 fallback weights")

    w1_str, b1_str, w2_str, b2_str = format_weights(w1, b1, w2, b2)

    # Replace weight placeholders in HEURISTIC_CODE
    code = HEURISTIC_CODE
    code = code.replace("W1_VALUES", w1_str)
    code = code.replace("B1_VALUES", b1_str)
    code = code.replace("W2_VALUES", w2_str)
    code = code.replace("B2_VALUES", b2_str)

    # Assemble final file
    header = f'''#!/usr/bin/env python3
"""
Chris - Nexus Wars Supreme Champion Agent v9.

v9: NES-optimized neural evaluator weights baked into v7 heuristic.
   - Neural evaluator (193 params) optimized via NES against
     fortress/viper/chimera/chimera-np
   - v7 heuristic preserved with all tactical features: orbital prediction,
     sun avoidance, sniping, coordinated strikes, energy management
   - No macro-action RL policy (proven ineffective ~50% win rate)
   - Single-file: no external dependencies, no network, no subprocess
   - Timeout: <1s per turn, RAM: <512MB
"""
'''

    content = header + code + ENTRYPOINT

    print(f"Total file size: {len(content)} bytes")

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Wrote: {OUT_PATH}")


if __name__ == '__main__':
    main()
