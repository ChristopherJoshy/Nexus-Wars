"""Fast callable opponent wrappers — bypass stdin/stdout JSON round-trip."""
import importlib.util, pathlib, math, os
import sys as _sys

_BASE = pathlib.Path(__file__).resolve().parent.parent / "test-bots"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Load opponent modules once
_fortress_mod = _load("fb_fortress", str(_BASE / "fortress.py"))
_viper_mod = _load("fb_viper", str(_BASE / "viper.py"))
_chimera_mod = _load("fb_chimera", str(_BASE / "chimera.py"))
_chimera_np_mod = _load("fb_chimera_np", str(_BASE / "chimera-np.py"))


def chimera_np_fast(obs):
    try:
        return _chimera_np_mod.decide(obs)
    except Exception:
        return []


def fortress_fast(obs):
    mod = _fortress_mod
    me = obs["player"]
    step = obs["step"]
    av = obs.get("angular_velocity", 0.035)
    planets = obs["planets"]
    fleets = obs.get("fleets", [])

    my_planets = [p for p in planets if p[1] == me]
    enemy_fleets_inbound = [f for f in fleets if f[1] != me]
    my_fleets_out = [f for f in fleets if f[1] == me]
    enemy_planets = [p for p in planets if p[1] != me and p[1] != -1]

    total_my_ships = sum(p[5] for p in my_planets) + sum(f[6] for f in my_fleets_out)
    total_enemy_ships = sum(p[5] for p in enemy_planets) + sum(f[6] for f in enemy_fleets_inbound)

    phase = "expand"
    if step > 150 or total_enemy_ships > total_my_ships * 0.6:
        phase = "consolidate"
    if step > 300 or total_my_ships > total_enemy_ships * 1.5:
        phase = "attack"

    actions = []

    for mp in my_planets:
        pid = mp[0]
        x, y, radius, ships = mp[2], mp[3], mp[4], mp[5]
        prod = mp[6]
        energy = mp[7]

        if ships < 3 or energy < 20:
            continue

        inbound_threat = 0
        threat_arrival = 999
        for f in enemy_fleets_inbound:
            d = mod.dist(mp, f)
            arr = d / mod.fleet_speed(f[6]) if f[6] > 0 else 999
            if arr < 25:
                inbound_threat += f[6]
                if arr < threat_arrival:
                    threat_arrival = arr

        min_keep = max(3, int(inbound_threat * 0.4)) + prod
        available = ships - min_keep
        if available < 5:
            if inbound_threat > 0 and available >= 3:
                own_fleets_here = [f for f in my_fleets_out if mod.dist(mp, f) < 20]
                own_help = sum(f[6] for f in own_fleets_here)
                if own_help < inbound_threat * 0.5:
                    reserves = [p for p in my_planets if p[0] != pid and p[5] > 15]
                    for res in sorted(reserves, key=lambda r: mod.dist(r, mp)):
                        if res[5] - 10 <= 0:
                            continue
                        send = min(res[5] - 10, inbound_threat - own_help + 5)
                        if send >= 3:
                            a = mod.angle_to(res[2], res[3], x, y)
                            actions.append([res[0], a, send])
                            break
            continue

        targets = []
        for t in planets:
            if t[1] == me:
                continue
            tx, ty = mod.orbital_pos(t, step, av)
            d = math.sqrt((x - tx) ** 2 + (y - ty) ** 2)
            if d < 1:
                d = 1
            ts = t[5]
            tp = t[6]
            towner = t[1]
            s = 0
            if phase == "expand":
                if towner == -1:
                    s = tp * 20 + 30 - ts * 1.0 - d * 0.3
                else:
                    s = tp * 10 + 15 - d * 0.5
            elif phase == "consolidate":
                if towner == -1:
                    s = tp * 25 - d * 0.2 - ts * 0.5
                else:
                    s = tp * 8 - d * 0.6
            else:
                if towner == -1:
                    s = tp * 10 - d * 0.1
                else:
                    need = ts * 2 + 5
                    if available >= need:
                        s = tp * 30 + 40 - d * 0.2 - ts * 0.3
                    else:
                        s = tp * 5 - d * 0.8
            targets.append((s, t, tx, ty, d))

        targets.sort(key=lambda x: -x[0])
        if not targets:
            continue

        best_score, best_t, btx, bty, bdist = targets[0]

        if phase == "expand":
            send = min(available, max(8, ships // 3))
            if send >= 5:
                a = mod.angle_to(x, y, btx, bty)
                actions.append([pid, a, send])
                available -= send
                if available >= 15 and len(targets) > 1:
                    s2 = targets[1]
                    s2_send = min(available, 10)
                    if s2_send >= 5:
                        a2 = mod.angle_to(x, y, s2[2], s2[3])
                        actions.append([pid, a2, s2_send])
        elif phase == "consolidate":
            save_ratio = 0.7 if prod >= 3 else 0.5
            send = min(available, max(10, int(ships * (1 - save_ratio))))
            if send >= 8:
                a = mod.angle_to(x, y, btx, bty)
                actions.append([pid, a, send])
        else:
            need = best_t[5] * 2 + 8
            send = min(available, max(need, 15))
            if send >= 10:
                a = mod.angle_to(x, y, btx, bty)
                actions.append([pid, a, send])

    return actions


def viper_fast(obs):
    mod = _viper_mod
    me = obs["player"]
    step = obs["step"]
    av = obs.get("angular_velocity", 0.035)
    planets = obs["planets"]
    fleets = obs.get("fleets", [])

    my_planets = [p for p in planets if p[1] == me]
    enemy_fleets = [f for f in fleets if f[1] != me]
    my_fleets = [f for f in fleets if f[1] == me]

    actions = []

    for mp in my_planets:
        pid, owner, x, y, radius, ships, prod, energy, ecap, eregen = mp

        if ships < 2 or energy < 20:
            continue

        threat = mod.defend_priority(mp, enemy_fleets, me)
        min_keep = max(5, int(threat * 0.3)) if threat > 0 else 3
        available = ships - min_keep
        if available < 5:
            continue

        targets = [p for p in planets if p[1] != me]
        if not targets:
            continue

        scored = []
        for t in targets:
            tx, ty = mod.orbital_pos(t, step, av)
            d = math.sqrt((x - tx) ** 2 + (y - ty) ** 2)
            tships = t[5]
            tprod = t[6]
            towner = t[1]
            s = tprod * 12
            if towner == -1:
                s += 15 - tships * 0.5
            else:
                s += 25 - tships * 1.0
            s -= d * 0.4
            scored.append((s, t, tx, ty, d))

        scored.sort(key=lambda x: -x[0])
        if not scored:
            continue

        best_score, best_target, btx, bty, bdist = scored[0]

        if len(scored) > 1 and available >= 30:
            second = scored[1]
            second_ships = min(available // 3, 15)
            if second_ships >= 8:
                s_angle = mod.angle_to(x, y, second[2], second[3])
                actions.append([pid, s_angle, second_ships])
                available -= second_ships

        send = min(available, max(8, ships // 2))
        if send > available:
            send = available
        angle = mod.angle_to(x, y, btx, bty)
        actions.append([pid, angle, send])
        available -= send

        if available - send >= 15 and len(scored) > 2:
            third = scored[2]
            t3_ships = min(available, 12)
            if t3_ships >= 6:
                t3_angle = mod.angle_to(x, y, third[2], third[3])
                actions.append([pid, t3_angle, t3_ships])

    return actions


def chimera_fast(obs):
    """Fast chimera using decide() — it's the numpy version's logic."""
    return chimera_np_fast(obs)


FAST_OPPONENTS = {
    "random": None,  # use engine random_agent
    "fortress": fortress_fast,
    "viper": viper_fast,
    "chimera": chimera_fast,
    "chimera-np": chimera_np_fast,
}
