"""AETHON: a fast, deterministic orbital-strategy bot for Nexus Wars.

The planner deliberately models the engine's tick order: a fleet launches from
the observed planet position, planets then sweep to their next orbital position,
and fleet/planet collisions are resolved continuously.  It uses a single
forward pass to forecast known fleets, then greedily assigns one well-sized
launch per planet.  This keeps turn time bounded as the number of fleets grows.
"""

import json
import math
import sys
import time


CENTER = 50.0
SUN = (50.0, 50.0)
SUN_RADIUS = 10.0
ROTATION_LIMIT = 50.0
LAUNCH_COST = 20
MAX_SPEED = 6.0
FORECAST_HORIZON = 72
DEFENCE_HORIZON = 48
TURN_BUDGET_SECONDS = 0.105
EPS = 1e-9

# A bot process serves one complete match.  Retaining each launch platform's
# current objective lets follow-up waves finish the garrison damage inflicted
# by the first wave instead of repeatedly starting new, unfinished attacks.
_memory = {"step": -1, "targets": {}}


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def fleet_speed(ships):
    if ships <= 0:
        return 0.0
    return min(
        MAX_SPEED,
        1.0 + 5.0 * (math.log(max(ships, 1)) / math.log(1000.0)) ** 1.5,
    )


def point_segment_distance(point, start, end):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_sq = dx * dx + dy * dy
    if length_sq <= EPS:
        return distance(point, start)
    t = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(point[0] - (start[0] + t * dx), point[1] - (start[1] + t * dy))


def swept_pair_hit(fleet_start, fleet_end, planet_start, planet_end, radius):
    """The same relative-motion collision test used by the game engine."""
    d0x = fleet_start[0] - planet_start[0]
    d0y = fleet_start[1] - planet_start[1]
    dvx = (fleet_end[0] - fleet_start[0]) - (planet_end[0] - planet_start[0])
    dvy = (fleet_end[1] - fleet_start[1]) - (planet_end[1] - planet_start[1])
    a = dvx * dvx + dvy * dvy
    b = 2.0 * (d0x * dvx + d0y * dvy)
    c = d0x * d0x + d0y * d0y - radius * radius
    if a <= EPS:
        return c <= 0.0
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        return False
    root = math.sqrt(discriminant)
    first = (-b - root) / (2.0 * a)
    second = (-b + root) / (2.0 * a)
    return second >= 0.0 and first <= 1.0


def is_orbiting(planet):
    return math.hypot(planet[2] - CENTER, planet[3] - CENTER) + planet[4] < ROTATION_LIMIT


def future_position(planet, initial_planets, step, turns_ahead, angular_velocity):
    """Position at the end of the resolution tick ``turns_ahead`` from now.

    At action step ``s`` the engine resolves planet motion to its initial
    orbital angle plus ``s * angular_velocity``.  Referencing the immutable
    initial planet record avoids the common double-rotation error.
    """
    initial = initial_planets.get(planet[0], planet)
    dx = initial[2] - CENTER
    dy = initial[3] - CENTER
    orbit_radius = math.hypot(dx, dy)
    if orbit_radius + planet[4] >= ROTATION_LIMIT:
        return initial[2], initial[3]
    absolute_tick = max(0, step + turns_ahead - 1)
    angle = math.atan2(dy, dx) + angular_velocity * absolute_tick
    return CENTER + orbit_radius * math.cos(angle), CENTER + orbit_radius * math.sin(angle)


def build_position_cache(planets, initial_planets, step, angular_velocity):
    """Cache orbital coordinates once per turn instead of recomputing them per ray."""
    return {
        planet[0]: [
            future_position(planet, initial_planets, step, tick, angular_velocity)
            for tick in range(FORECAST_HORIZON + 1)
        ]
        for planet in planets
    }


def launch_intercept(
    source,
    target,
    ships,
    initial_planets,
    step,
    angular_velocity,
    position_cache=None,
):
    """Return ``(arrival_tick, angle)`` for a safe direct moving-planet hit.

    We test every practical arrival tick with the engine's swept-pair test;
    this is both more reliable than a rounded distance estimate and inexpensive
    for the small fixed board.
    """
    speed = fleet_speed(ships)
    if speed <= 0.0:
        return None

    source_center = (source[2], source[3])
    for tick in range(1, FORECAST_HORIZON + 1):
        target_end = (
            position_cache[target[0]][tick]
            if position_cache is not None
            else future_position(target, initial_planets, step, tick, angular_velocity)
        )
        dx = target_end[0] - source_center[0]
        dy = target_end[1] - source_center[1]
        span = math.hypot(dx, dy)
        if span <= EPS:
            continue
        angle = math.atan2(dy, dx)
        ux = dx / span
        uy = dy / span
        fleet_start = (
            source_center[0] + ux * (source[4] + 0.1),
            source_center[1] + uy * (source[4] + 0.1),
        )
        fleet_before = (
            fleet_start[0] + ux * speed * (tick - 1),
            fleet_start[1] + uy * speed * (tick - 1),
        )
        fleet_after = (
            fleet_before[0] + ux * speed,
            fleet_before[1] + uy * speed,
        )
        target_start = (
            position_cache[target[0]][tick - 1]
            if position_cache is not None
            else future_position(target, initial_planets, step, tick - 1, angular_velocity)
        )
        if not swept_pair_hit(fleet_before, fleet_after, target_start, target_end, target[4]):
            continue
        # A direct course which crosses the sun is always vaporised before a
        # destination collision.  A small margin protects floating boundaries.
        if point_segment_distance(SUN, fleet_start, target_end) <= SUN_RADIUS + 0.05:
            return None
        return tick, angle
    return None


def predict_fleet_arrivals(
    planets,
    fleets,
    initial_planets,
    step,
    angular_velocity,
    position_cache=None,
):
    """Find known fleet impacts in one pass using a small ray-local candidate set."""
    arrivals = {}
    for fleet in fleets:
        ships = fleet[6]
        speed = fleet_speed(ships)
        if speed <= 0.0:
            continue
        ux = math.cos(fleet[4])
        uy = math.sin(fleet[4])
        candidates = []
        for planet in planets:
            rx = planet[2] - fleet[2]
            ry = planet[3] - fleet[3]
            forward = rx * ux + ry * uy
            estimate = forward / speed
            if estimate < -8.0 or estimate > FORECAST_HORIZON + 8.0:
                continue
            perpendicular = abs(rx * uy - ry * ux)
            # Fleets aimed at an orbiting target remain close to its current
            # ray; retaining a bounded candidate set keeps late-game turns fast.
            candidates.append((perpendicular + 0.03 * abs(estimate), estimate, planet))
        candidates.sort(key=lambda item: item[0])

        best = None
        for _, estimate, planet in candidates[:12]:
            start_tick = max(1, int(math.floor(estimate)) - 10)
            end_tick = min(FORECAST_HORIZON, int(math.ceil(estimate)) + 12)
            for tick in range(start_tick, end_tick + 1):
                before = (
                    fleet[2] + ux * speed * (tick - 1),
                    fleet[3] + uy * speed * (tick - 1),
                )
                after = (before[0] + ux * speed, before[1] + uy * speed)
                if position_cache is None:
                    planet_before = future_position(
                        planet, initial_planets, step, tick - 1, angular_velocity
                    )
                    planet_after = future_position(
                        planet, initial_planets, step, tick, angular_velocity
                    )
                else:
                    planet_before = position_cache[planet[0]][tick - 1]
                    planet_after = position_cache[planet[0]][tick]
                if swept_pair_hit(before, after, planet_before, planet_after, planet[4]):
                    candidate = (tick, planet[0])
                    if best is None or candidate < best[:2]:
                        best = (tick, planet[0], fleet[1], ships)
                    break
        if best is not None:
            tick, planet_id, owner, force = best
            per_planet = arrivals.setdefault(planet_id, {})
            per_tick = per_planet.setdefault(tick, {})
            per_tick[owner] = per_tick.get(owner, 0) + force
    return arrivals


def resolve_arrivals(owner, ships, forces):
    """Resolve same-tick attacker clash followed by the garrison battle."""
    if not forces:
        return owner, ships
    ranked = sorted(forces.items(), key=lambda item: item[1], reverse=True)
    attacker, surviving = ranked[0]
    if len(ranked) > 1:
        surviving -= ranked[1][1]
    if surviving <= 0:
        return owner, ships
    if attacker == owner:
        return owner, ships + surviving
    remaining = ships - surviving
    if remaining < 0:
        return attacker, -remaining
    return owner, remaining


def build_timelines(planets, arrivals, horizon):
    """Forecast garrison/ownership once; all later queries are O(1)."""
    timelines = {}
    for planet in planets:
        owner = planet[1]
        ships = planet[5]
        line = [(owner, ships)]
        planet_arrivals = arrivals.get(planet[0], {})
        for tick in range(1, horizon + 1):
            if owner != -1:
                ships += planet[6]
            owner, ships = resolve_arrivals(owner, ships, planet_arrivals.get(tick))
            line.append((owner, ships))
        timelines[planet[0]] = line
    return timelines


def capacity_and_deadline(planet, timeline, player, step):
    """Ships that can leave without exposing this planet to known impacts."""
    minimum = planet[5]
    for tick, (owner, ships) in enumerate(timeline[1:DEFENCE_HORIZON + 1], start=1):
        if owner != player:
            return 0, tick
        minimum = min(minimum, ships)
    # Preserve a small standing garrison even during expansion.  In the first
    # minute a quiet home may commit all but one ship to open a rich neutral;
    # once a known impact erodes the forecast, the full two-ship buffer applies.
    reserve = 0 if step == 0 else (1 if step < 60 and minimum >= planet[5] else 2)
    return max(0, minimum - reserve), None


def launch_solution(
    source,
    target,
    capacity,
    timelines,
    initial_planets,
    step,
    angular_velocity,
    player,
    allow_follow_up=False,
    position_cache=None,
):
    """Iterate ship count/ETA twice because fleet speed changes with force."""
    send = capacity
    for _ in range(3):
        intercept = launch_intercept(
            source,
            target,
            send,
            initial_planets,
            step,
            angular_velocity,
            position_cache,
        )
        if intercept is None:
            return None
        arrival_tick, angle = intercept
        owner, ships = timelines[target[0]][arrival_tick]
        if owner == player:
            return None
        required = ships + 1
        if required > capacity:
            # A failed attack is not all-or-nothing in Nexus Wars: it removes
            # its force from the garrison before the surviving defender remains.
            # Opening a high-production neutral with a force that removes at
            # least half its garrison is often superior to waiting while AEGIS
            # captures it in two waves.
            attrition_force = max(7, int(math.ceil(ships * 0.35)))
            if target[6] >= 3 and (
                capacity >= attrition_force or (allow_follow_up and capacity >= 4)
            ):
                return arrival_tick, angle, capacity, owner, ships
            return None
        guarded_send = min(capacity, required + max(1, int(math.ceil(required * 0.12))))
        if guarded_send == send:
            return arrival_tick, angle, send, owner, ships
        send = guarded_send
    return arrival_tick, angle, send, owner, ships


def target_score(target, arrival_tick, owner, ships, step, player, my_production, enemy_production):
    """A value function that changes smoothly from expansion to conversion."""
    remaining = max(0, 500 - step - arrival_tick)
    score = target[6] * (44.0 + min(36.0, remaining * 0.12))
    score -= ships * 2.25 + arrival_tick * 2.1

    if owner == -1:
        score += 95.0 if step < 150 else 35.0
    else:
        score += 28.0 + target[6] * 12.0
        if step < 85 and my_production <= enemy_production:
            score -= 70.0
        if step > 360:
            score += 50.0
    return score


def act(observation):
    turn_started = time.perf_counter()
    player = observation["player"]
    step = observation["step"]
    angular_velocity = observation.get("angular_velocity", 0.035)
    planets = observation.get("planets", [])
    fleets = observation.get("fleets", [])
    initial_planets = {planet[0]: planet for planet in observation.get("initial_planets", planets)}

    mine = [planet for planet in planets if planet[1] == player]
    if not mine:
        return []

    if step == 0 or step <= _memory["step"]:
        _memory["targets"] = {}
    _memory["step"] = step

    position_cache = build_position_cache(planets, initial_planets, step, angular_velocity)

    arrivals = predict_fleet_arrivals(
        planets,
        fleets,
        initial_planets,
        step,
        angular_velocity,
        position_cache,
    )
    timelines = build_timelines(planets, arrivals, FORECAST_HORIZON)
    enemy = [planet for planet in planets if planet[1] not in (-1, player)]
    my_production = sum(planet[6] for planet in mine)
    enemy_production = sum(planet[6] for planet in enemy)

    capacities = {}
    threatened = []
    for planet in mine:
        capacity, deadline = capacity_and_deadline(
            planet, timelines[planet[0]], player, step
        )
        capacities[planet[0]] = capacity
        if deadline is not None:
            threatened.append((deadline, planet))

    actions = []
    used_sources = set()

    # First preserve planets that known enemy fleets would otherwise capture.
    for deadline, target in sorted(threatened, key=lambda item: item[0]):
        best = None
        for source in mine:
            if source[0] == target[0] or source[0] in used_sources:
                continue
            capacity = capacities[source[0]]
            if capacity < 2 or source[7] < LAUNCH_COST:
                continue
            maximum = launch_intercept(
                source,
                target,
                capacity,
                initial_planets,
                step,
                angular_velocity,
                position_cache,
            )
            if maximum is None or maximum[0] > deadline:
                continue
            # A captured forecast exposes the post-combat enemy remainder;
            # that remainder plus a buffer is the reinforcement we need.
            owner_at_deadline, ships_at_deadline = timelines[target[0]][deadline]
            needed = max(3, ships_at_deadline + 3 if owner_at_deadline != player else 3)
            send = min(capacity, max(needed, int(math.ceil(needed * 1.12))))
            intercept = launch_intercept(
                source,
                target,
                send,
                initial_planets,
                step,
                angular_velocity,
                position_cache,
            )
            if intercept is None or intercept[0] > deadline:
                continue
            candidate = (intercept[0], -send, source, intercept)
            if best is None or candidate[:2] < best[:2]:
                best = candidate
        if best is not None:
            _, _, source, intercept = best
            send = -best[1]
            actions.append([source[0], intercept[1], send])
            capacities[source[0]] -= send
            used_sources.add(source[0])

    # Evaluate every pairing once, then take the best conflict-free matching.
    # This recovers global target assignment (a nearby smaller planet can claim
    # a prize before a distant armada does) without the old quadratic rescore.
    claimable = [planet for planet in planets if planet[1] != player]
    claimed = set()
    pairings = []
    for source in mine:
        if time.perf_counter() - turn_started >= TURN_BUDGET_SECONDS:
            break
        source_id = source[0]
        if source_id in used_sources or source[7] < LAUNCH_COST:
            continue
        capacity = capacities[source_id]
        if capacity < 2:
            continue
        for target in claimable:
            if target[0] in claimed:
                continue
            is_follow_up = _memory["targets"].get(source_id) == target[0]
            solution = launch_solution(
                source,
                target,
                capacity,
                timelines,
                initial_planets,
                step,
                angular_velocity,
                player,
                is_follow_up,
                position_cache,
            )
            if solution is None:
                continue
            arrival_tick, angle, send, future_owner, future_ships = solution
            score = target_score(
                target,
                arrival_tick,
                future_owner,
                future_ships,
                step,
                player,
                my_production,
                enemy_production,
            )
            if is_follow_up:
                score += 60.0
            pairings.append((score, source_id, target[0], source, target, solution))

    pairings.sort(key=lambda pairing: pairing[0], reverse=True)
    for score, source_id, target_id, source, target, solution in pairings:
        if score <= 0.0:
            break
        if source_id in used_sources or target_id in claimed:
            continue
        _, angle, send, _, _ = solution
        actions.append([source[0], angle, send])
        capacities[source[0]] -= send
        used_sources.add(source[0])
        claimed.add(target_id)
        _memory["targets"][source[0]] = target[0]

    return actions


def main():
    for line in sys.stdin:
        try:
            observation = json.loads(line)
            print(json.dumps(act(observation)), flush=True)
        except Exception:
            # Protocol failures are safer as a no-op; never write diagnostics
            # to stdout because it is the action channel.
            print("[]", flush=True)


if __name__ == "__main__":
    main()
