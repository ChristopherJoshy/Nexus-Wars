#!/usr/bin/env python3
import json
import math
import os
import sys
import time
import traceback

# Set NEXUS_DEBUG to a file path to trace planning decisions (the harness
# swallows bot stderr, so diagnostics go to their own file).
DEBUG = os.environ.get("NEXUS_DEBUG")
_dbg = open(DEBUG, "a", buffering=1) if DEBUG else None

# --- Engine constants (nexus_wars.py) -------------------------------------
BOARD = 100.0
C = 50.0
SUN_R = 10.0
ROT_LIMIT = 50.0
MAX_SPEED = 6.0
LAUNCH_COST = 20
LAUNCH_OFFSET = 0.1          # engine spawns fleets at radius + 0.1

# --- Tunables -------------------------------------------------------------
SUN_PAD = 1.8                # clearance over the hard 10.0 kill radius
HORIZON = 60                 # planning depth, ticks (upper bound)
HORIZON_MIN = 26             # floor when the board is heavy
WORK_BUDGET = 90000          # fleets * planets * ticks we allow per turn
TIME_BUDGET = 0.055          # seconds of planning before we bail out safely
MAX_POOL = 8                 # max planets pooled into one ToT strike
MAX_PLANS = 4                # max NEW strikes opened per turn
MAX_TARGETS = 18             # target shortlist size
TOT_WINDOW = 8               # extra arrival ticks probed past the earliest
BASE_KEEP = 3                # baseline garrison never spent
FRONT_KEEP = 8               # extra garrison held on frontline planets
FRONT_DIST = 30.0            # "frontline" = this close to an enemy planet
MIN_FLEET = 3
HUB_MIN_FLEET = 10           # a logistics run must be worth its 20 energy
HUB_GAIN = 1.15              # rear planet must be this much further out
CAPACITY_SAFETY = 1.08       # pooled supply must beat demand by this factor
PROD_W = 26.0
NEUTRAL_BONUS = 34.0
ENEMY_BONUS = 20.0
TIME_W = 1.35
COMMIT_BONUS = 45.0          # bias toward targets we already committed to
MAX_ACTIVE_PLANS = 6         # cap on simultaneously open ToT plans
PLAN_STALE = 10              # drop an unstarted plan after this many turns

_SPEED_CACHE = {}


def fleet_speed(ships):
    """Engine: speed = 1 + (max-1) * (ln(n)/ln(1000))**1.5, capped."""
    n = int(ships)
    if n <= 1:
        return 1.0
    v = _SPEED_CACHE.get(n)
    if v is None:
        v = min(MAX_SPEED, 1.0 + (MAX_SPEED - 1.0) * (math.log(n) / math.log(1000)) ** 1.5)
        if len(_SPEED_CACHE) < 20000:
            _SPEED_CACHE[n] = v
    return v


def seg_point_dist2(px, py, ax, ay, bx, by):
    """Squared distance from a point to a segment."""
    dx = bx - ax
    dy = by - ay
    l2 = dx * dx + dy * dy
    if l2 <= 1e-12:
        ex = px - ax
        ey = py - ay
        return ex * ex + ey * ey
    t = ((px - ax) * dx + (py - ay) * dy) / l2
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    ex = ax + t * dx - px
    ey = ay + t * dy - py
    return ex * ex + ey * ey


def sun_path_clear(ax, ay, bx, by):
    r = SUN_R + SUN_PAD
    return seg_point_dist2(C, C, ax, ay, bx, by) > r * r


def swept_hit(ax, ay, bx, by, p0x, p0y, p1x, p1y, r):
    """Continuous swept-pair collision -- reproduced from the interpreter.

    True iff a fleet moving A->B and a planet moving P0->P1 come within r of
    each other for some t in [0, 1].
    """
    d0x = ax - p0x
    d0y = ay - p0y
    dvx = (bx - ax) - (p1x - p0x)
    dvy = (by - ay) - (p1y - p0y)
    a = dvx * dvx + dvy * dvy
    b = 2.0 * (d0x * dvx + d0y * dvy)
    c = d0x * d0x + d0y * d0y - r * r
    if a < 1e-12:
        return c <= 0.0
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return False
    sq = math.sqrt(disc)
    inv = 1.0 / (2.0 * a)
    t1 = (-b - sq) * inv
    t2 = (-b + sq) * inv
    return t2 >= 0.0 and t1 <= 1.0


class World:
    """Per-turn precomputation shared by every planner."""

    def __init__(self, obs, me):
        self.me = me
        self.step = obs.get("step", 0)
        self.av = obs.get("angular_velocity", 0.035)
        self.planets = obs.get("planets", []) or []
        self.fleets = obs.get("fleets", []) or []
        self.n = len(self.planets)
        self.idx = {p[0]: i for i, p in enumerate(self.planets)}

        # Scale planning depth to the board so a busy turn cannot blow the
        # harness' per-turn timeout on slow or contended hardware.
        load = max(1, len(self.fleets)) * max(1, self.n)
        h = WORK_BUDGET // load
        self.H = max(HORIZON_MIN, min(HORIZON, h))

        self.radius = [p[4] for p in self.planets]
        self.orb_r = []
        self.orb_a = []
        self.rotates = []
        for p in self.planets:
            dx = p[2] - C
            dy = p[3] - C
            r = math.sqrt(dx * dx + dy * dy)
            self.orb_r.append(r)
            self.orb_a.append(math.atan2(dy, dx))
            # The rotation test is radius-based and rotation-invariant, so the
            # observed position serves as well as the initial one.
            self.rotates.append(r + p[4] < ROT_LIMIT)

        self._build_positions()
        self._k_cache = {}

    def _build_positions(self):
        """PX[t][i], PY[t][i] = position of planet i, t ticks from now.

        Advanced by complex rotor multiplication -- no trig in the inner loop.
        """
        n = self.n
        w = complex(math.cos(self.av), math.sin(self.av))
        cur = [complex(p[2] - C, p[3] - C) for p in self.planets]
        rot = self.rotates
        PX = []
        PY = []
        for _ in range(self.H + 1):
            PX.append([C + z.real for z in cur])
            PY.append([C + z.imag for z in cur])
            cur = [(cur[i] * w if rot[i] else cur[i]) for i in range(n)]
        self.PX = PX
        self.PY = PY

    # -- kinematics --------------------------------------------------------
    def intercept(self, sx, sy, r_src, j, v):
        """Kinematic root-finder: damped fixed point on continuous flight time.

        Returns (k, aim_x, aim_y), k being the exact tick the fleet lands.
        Damping kills the two-cycle oscillation an integer fixed point falls
        into when the target straddles a ceil() boundary.
        """
        rt = self.radius[j]
        slack = r_src + LAUNCH_OFFSET + rt
        if not self.rotates[j]:
            tx = self.PX[0][j]
            ty = self.PY[0][j]
            d = math.hypot(tx - sx, ty - sy)
            return max(1, int(math.ceil((d - slack) / v))), tx, ty

        R = self.orb_r[j]
        a0 = self.orb_a[j]
        av = self.av
        t = 1.0
        for _ in range(8):
            a = a0 + av * t
            x = C + R * math.cos(a)
            y = C + R * math.sin(a)
            nt = (math.hypot(x - sx, y - sy) - slack) / v
            if nt < 0.5:
                nt = 0.5
            if abs(nt - t) < 1e-3:
                t = nt
                break
            t = 0.5 * (t + nt)
        a = a0 + av * t
        x = C + R * math.cos(a)
        y = C + R * math.sin(a)
        k = max(1, int(math.ceil((math.hypot(x - sx, y - sy) - slack) / v)))
        return k, x, y

    def arrival(self, i, j, ships):
        """Cached (k, aim_x, aim_y) for planet i striking planet j."""
        v = fleet_speed(ships)
        key = (i, j, int(v * 20.0))
        got = self._k_cache.get(key)
        if got is None:
            p = self.planets[i]
            got = self.intercept(p[2], p[3], self.radius[i], j, v)
            self._k_cache[key] = got
        return got

    def simulate_launch(self, i, ships, aim_x, aim_y):
        """Replay a prospective launch through engine rules.

        Returns (hit_index, tick) or (None, None).  This is the gate that
        catches fleets absorbed by a third planet, killed by the Sun, or flung
        off the board -- the engine stops a fleet at the FIRST planet its swept
        segment touches, iterating the planet list in order.
        """
        p = self.planets[i]
        ang = math.atan2(aim_y - p[3], aim_x - p[2])
        ca = math.cos(ang)
        sa = math.sin(ang)
        v = fleet_speed(ships)
        cx = p[2] + ca * (self.radius[i] + LAUNCH_OFFSET)
        cy = p[3] + sa * (self.radius[i] + LAUNCH_OFFSET)
        vx = v * ca
        vy = v * sa
        n = self.n
        rad = self.radius
        orb = self.orb_r
        for t in range(self.H):
            nx = cx + vx
            ny = cy + vy
            rx0 = self.PX[t]
            ry0 = self.PY[t]
            rx1 = self.PX[t + 1]
            ry1 = self.PY[t + 1]
            d2 = seg_point_dist2(C, C, cx, cy, nx, ny)
            dmin = math.sqrt(d2)
            dmax = max(math.hypot(cx - C, cy - C), math.hypot(nx - C, ny - C))
            for q in range(n):
                rr = rad[q]
                R = orb[q]
                if R + rr < dmin - 0.5 or R - rr > dmax + 0.5:
                    continue
                if swept_hit(cx, cy, nx, ny, rx0[q], ry0[q], rx1[q], ry1[q], rr):
                    return q, t + 1
            if d2 < SUN_R * SUN_R:
                return None, None
            if nx < 0.0 or nx > BOARD or ny < 0.0 or ny > BOARD:
                return None, None
            cx = nx
            cy = ny
        return None, None

    # -- predictive state --------------------------------------------------
    def simulate_arrivals(self):
        """March every in-flight fleet forward; record where and when it lands."""
        n = self.n
        rad = self.radius
        orb = self.orb_r
        arrivals = [[] for _ in range(n)]
        for f in self.fleets:
            ships = f[6]
            if ships <= 0:
                continue
            v = fleet_speed(ships)
            ang = f[4]
            vx = v * math.cos(ang)
            vy = v * math.sin(ang)
            cx = f[2]
            cy = f[3]
            owner = f[1]
            for t in range(self.H):
                nx = cx + vx
                ny = cy + vy
                rx0 = self.PX[t]
                ry0 = self.PY[t]
                rx1 = self.PX[t + 1]
                ry1 = self.PY[t + 1]
                d2 = seg_point_dist2(C, C, cx, cy, nx, ny)
                dmin = math.sqrt(d2)
                dmax = max(math.hypot(cx - C, cy - C), math.hypot(nx - C, ny - C))
                hit = -1
                for q in range(n):
                    rr = rad[q]
                    R = orb[q]
                    if R + rr < dmin - 0.5 or R - rr > dmax + 0.5:
                        continue
                    if swept_hit(cx, cy, nx, ny, rx0[q], ry0[q], rx1[q], ry1[q], rr):
                        hit = q
                        break
                if hit >= 0:
                    arrivals[hit].append((t + 1, ships, owner))
                    break
                if d2 < SUN_R * SUN_R:
                    break
                if nx < 0.0 or nx > BOARD or ny < 0.0 or ny > BOARD:
                    break
                cx = nx
                cy = ny
        return arrivals

    def project(self, arrivals):
        """Forward-simulate owner/garrison per planet over the horizon.

        Mirrors interpreter ordering: production first, then combat, with all
        fleets of one player on a tick SUMMED before the top-two subtraction.
        """
        owners = []
        ships = []
        for i, p in enumerate(self.planets):
            ev = {}
            for (t, s, o) in arrivals[i]:
                ev.setdefault(t, []).append((s, o))
            own = p[1]
            sh = p[5]
            prod = p[6]
            os_ = [own] * (self.H + 1)
            ss = [sh] * (self.H + 1)
            for t in range(1, self.H + 1):
                if own != -1:
                    sh += prod
                lst = ev.get(t)
                if lst:
                    agg = {}
                    for s, o in lst:
                        agg[o] = agg.get(o, 0) + s
                    srt = sorted(agg.items(), key=lambda kv: -kv[1])
                    top_o, top_s = srt[0]
                    if len(srt) > 1:
                        surv = top_s - srt[1][1]
                        surv_o = top_o if surv > 0 else -1
                    else:
                        surv = top_s
                        surv_o = top_o
                    if surv > 0:
                        if own == surv_o:
                            sh += surv
                        else:
                            sh -= surv
                            if sh < 0:
                                own = surv_o
                                sh = -sh
                os_[t] = own
                ss[t] = sh
            owners.append(os_)
            ships.append(ss)
        return owners, ships


def build_threat_matrix(world, owners, ships):
    """Predictive state simulation -> {planet_index: (critical_tick, deficit)}.

    Semantics preserved from the original: the first tick at which a planet we
    own changes hands, and how many extra ships would have held it.
    """
    compromised = {}
    me = world.me
    for i, p in enumerate(world.planets):
        if p[1] != me:
            continue
        row = owners[i]
        for t in range(1, world.H + 1):
            if row[t] != me:
                compromised[i] = (t, ships[i][t] + 1)
                break
    return compromised


def get_best_relay(world, i, j, ships, friendly):
    """Graph-theory relay routing around the Sun, with thermodynamic delay.

    Restricted to planets WE own: a fleet landing anywhere else fights instead
    of relaying, so only a friendly node is a real waypoint.  Cost includes the
    wait for that node to regenerate launch energy.
    """
    p = world.planets[i]
    best = None
    best_t = float("inf")
    v = fleet_speed(ships)
    for r in friendly:
        if r == i or r == j:
            continue
        k1, rx, ry = world.arrival(i, r, ships)
        if k1 > world.H - 4 or not sun_path_clear(p[2], p[3], rx, ry):
            continue
        rp = world.planets[r]
        k2, tx, ty = world.intercept(rx, ry, world.radius[r], j, v)
        if not sun_path_clear(rx, ry, tx, ty):
            continue
        deficit = LAUNCH_COST - rp[7]
        delay = int(math.ceil(deficit / rp[9])) if deficit > 0 and rp[9] > 0 else 0
        total = k1 + max(0, delay) + k2
        if total < best_t:
            best_t = total
            best = (r, rx, ry)
    return best


class Commander:
    """Holds Time-on-Target plans across turns.

    A plan is {target planet id -> {"arrive": absolute step, "alloc":
    {source planet id: ships}, "sent": {source planet id}}}.  Storing the
    ABSOLUTE arrival step is what keeps a staggered strike coherent: fleets
    already in flight are never orphaned by the next turn's re-planning.
    """

    def __init__(self):
        self.plans = {}
        # Own clock.  obs["step"] is NOT reliable: the harness assigns
        # observation.step to player 0 only (run_match.py), so player 1 sees
        # step == 0 for the whole match.  We are called exactly once per turn,
        # so counting calls is exact for both seats.
        self.turn = 0

    # -- helpers -----------------------------------------------------------
    def _prune(self, world, owners, step):
        """Drop plans that are finished, impossible, or no longer worthwhile."""
        me = world.me
        for tid in list(self.plans.keys()):
            pl = self.plans[tid]
            j = world.idx.get(tid)
            if j is None or pl["arrive"] <= step:
                del self.plans[tid]
                continue
            # An unstarted plan that has gone stale is capital left idle.
            if not pl["sent"] and step - pl["opened"] > PLAN_STALE:
                del self.plans[tid]
                continue
            # Target already ours (or will be) at the strike tick: stand down.
            rem = pl["arrive"] - step
            if rem <= world.H and owners[j][rem] == me and not pl["sent"]:
                del self.plans[tid]
                continue
            # Contributors that are no longer ours cannot deliver.
            for sid in list(pl["alloc"].keys()):
                si = world.idx.get(sid)
                if si is None or world.planets[si][1] != me:
                    pl["alloc"].pop(sid, None)
                    pl["sent"].discard(sid)
            if not pl["alloc"]:
                del self.plans[tid]

    def act(self, obs, deadline):
        me = obs["player"]
        world = World(obs, me)
        n = world.n
        if n == 0:
            return []
        planets = world.planets
        step = self.turn
        self.turn += 1
        mine = [i for i in range(n) if planets[i][1] == me]
        if not mine:
            self.plans.clear()
            return []

        arrivals = world.simulate_arrivals()
        owners, proj = world.project(arrivals)
        compromised = build_threat_matrix(world, owners, proj)
        self._prune(world, owners, step)

        v_ships = {i: planets[i][5] for i in mine}
        v_energy = {i: planets[i][7] for i in mine}
        launched = set()
        actions = []

        enemy_ids = [i for i in range(n) if planets[i][1] not in (me, -1)]

        enemy_dist = {}
        for i in mine:
            p = planets[i]
            best = float("inf")
            for j in enemy_ids:
                q = planets[j]
                d = math.hypot(p[2] - q[2], p[3] - q[3])
                if d < best:
                    best = d
            enemy_dist[i] = best

        # Garrison we refuse to spend.
        keep = {}
        for i in mine:
            inc_e = 0
            inc_f = 0
            for (t, s, o) in arrivals[i]:
                if t <= 20:
                    if o == me:
                        inc_f += s
                    else:
                        inc_e += s
            k = BASE_KEEP + max(0, inc_e - inc_f)
            if enemy_dist[i] < FRONT_DIST:
                k += FRONT_KEEP
            keep[i] = min(k, planets[i][5])

        # Ships already promised to open ToT plans.
        reserved = {i: 0 for i in mine}
        for pl in self.plans.values():
            for sid, cnt in pl["alloc"].items():
                if sid in pl["sent"]:
                    continue
                si = world.idx.get(sid)
                if si in reserved:
                    reserved[si] += cnt

        def free(i):
            return v_ships[i] - keep[i] - reserved.get(i, 0)

        def commit(i, aim_x, aim_y, ships):
            """Gate a launch through engine rules, then record it."""
            ships = int(ships)
            if ships < 1 or ships > v_ships[i] or v_energy[i] < LAUNCH_COST:
                return False
            p = planets[i]
            if not sun_path_clear(p[2], p[3], aim_x, aim_y):
                return False
            actions.append([p[0], math.atan2(aim_y - p[3], aim_x - p[2]), ships])
            v_ships[i] -= ships
            v_energy[i] -= LAUNCH_COST
            launched.add(i)
            return True

        # --------------------------------------------------------------
        # PHASE 1 -- Defence, allocated before any offensive ship is spent.
        # --------------------------------------------------------------
        for j, (crit, deficit) in sorted(compromised.items(), key=lambda kv: kv[1][0]):
            need = deficit
            helpers = []
            for i in mine:
                if i == j or i in launched or v_energy[i] < LAUNCH_COST:
                    continue
                avail = v_ships[i] - keep[i]
                if avail < MIN_FLEET:
                    continue
                k, ax, ay = world.arrival(i, j, avail)
                if k <= crit:
                    helpers.append((k, i, avail, ax, ay))
            helpers.sort()
            for k, i, avail, ax, ay in helpers:
                if need <= 0:
                    break
                send = min(avail, need)
                if send < MIN_FLEET:
                    continue
                k2, ax2, ay2 = world.arrival(i, j, send)
                if k2 > crit:
                    send = avail                      # buy speed with mass
                    k2, ax2, ay2 = world.arrival(i, j, send)
                    if k2 > crit:
                        continue
                hit, tick = world.simulate_launch(i, send, ax2, ay2)
                if hit != j or tick > crit:
                    continue
                if commit(i, ax2, ay2, send):
                    need -= send
                    reserved[i] = 0                   # emergency overrides plans

        if time.monotonic() > deadline:
            return actions

        # --------------------------------------------------------------
        # PHASE 2a -- Execute due launches of existing ToT plans.
        # --------------------------------------------------------------
        for tid in list(self.plans.keys()):
            pl = self.plans[tid]
            j = world.idx.get(tid)
            if j is None:
                continue
            rem = pl["arrive"] - step
            if rem < 1 or rem > world.H:
                continue
            for sid in list(pl["alloc"].keys()):
                if sid in pl["sent"]:
                    continue
                i = world.idx.get(sid)
                if i is None or i in launched or i not in v_ships:
                    continue
                want = pl["alloc"][sid]
                if v_energy[i] < LAUNCH_COST:
                    continue
                if want > v_ships[i]:
                    want = v_ships[i]
                if want < MIN_FLEET:
                    continue
                k, ax, ay = world.arrival(i, j, want)
                if k < rem:
                    continue                          # too early; wait a turn
                if k > rem:
                    # Running late -- spend mass to buy the speed back.
                    boost = min(v_ships[i] - keep[i], v_ships[i])
                    if boost > want:
                        k2, ax2, ay2 = world.arrival(i, j, boost)
                        if k2 == rem:
                            want, k, ax, ay = boost, k2, ax2, ay2
                    if k > rem:
                        continue
                hit, tick = world.simulate_launch(i, want, ax, ay)
                if hit != j or tick != rem:
                    continue
                if commit(i, ax, ay, want):
                    pl["sent"].add(sid)
                    reserved[i] = max(0, reserved.get(i, 0) - pl["alloc"][sid])

        if time.monotonic() > deadline:
            return actions

        # --------------------------------------------------------------
        # PHASE 2b -- Open new Time-on-Target plans.
        # --------------------------------------------------------------
        my_cx = sum(planets[i][2] for i in mine) / len(mine)
        my_cy = sum(planets[i][3] for i in mine) / len(mine)
        shortlist = []
        for j in range(n):
            if planets[j][1] == me or planets[j][0] in self.plans:
                continue
            p = planets[j]
            d = math.hypot(p[2] - my_cx, p[3] - my_cy)
            val = p[6] * PROD_W + (NEUTRAL_BONUS if p[1] == -1 else ENEMY_BONUS)
            inbound = any(o == me for (_, _, o) in arrivals[j])
            shortlist.append((-(val - d * 0.9 - p[5] * 0.30 +
                                (COMMIT_BONUS if inbound else 0.0)), j))
        shortlist.sort()
        shortlist = [j for _, j in shortlist[:MAX_TARGETS]]

        def demand(j, T):
            """Ships needed to take planet j on tick T, given all in flight."""
            if owners[j][T] == me:
                return -1
            g = proj[j][T]
            return g + 2 + int(g * 0.02)

        def plan_target(j, avail_src):
            """Pool planets so their fleets land on planet j together.

            Every contributor must already HOLD its allocated ships: a strike
            is never opened on the promise of future production, which is what
            leaves a lone fleet stranded against a full garrison.
            """
            cands = []
            for i in avail_src:
                cap = free(i)
                if cap < MIN_FLEET:
                    continue
                k, ax, ay = world.arrival(i, j, cap)
                if k > world.H - 4:
                    continue
                if not sun_path_clear(planets[i][2], planets[i][3], ax, ay):
                    continue
                cands.append((k, i))
            if not cands:
                return None
            cands.sort()

            for m in range(1, min(MAX_POOL, len(cands)) + 1):
                if time.monotonic() > deadline:
                    return None
                subset = [i for _, i in cands[:m]]
                T = cands[m - 1][0]
                for _ in range(TOT_WINDOW):
                    if T > world.H - 4:
                        break
                    need = demand(j, T)
                    if need < 0:
                        return None
                    supply = []
                    total = 0
                    for i in subset:
                        cap = free(i)
                        if cap < MIN_FLEET:
                            continue
                        k, _, _ = world.arrival(i, j, cap)
                        if k > T:
                            continue                  # cannot make this tick
                        d = T - k
                        if v_energy[i] + planets[i][9] * d < LAUNCH_COST:
                            continue
                        supply.append((cap, i))
                        total += cap
                    if total >= need * CAPACITY_SAFETY:
                        supply.sort(reverse=True)
                        alloc = {}
                        rem = need
                        for cap, i in supply:
                            if rem <= 0:
                                break
                            take = int(min(cap, rem))
                            if take < MIN_FLEET:
                                take = int(min(cap, MIN_FLEET))
                            k2, _, _ = world.arrival(i, j, take)
                            if k2 > T:
                                take = int(cap)       # buy speed with mass
                                k2, _, _ = world.arrival(i, j, take)
                                if k2 > T:
                                    continue
                            alloc[planets[i][0]] = take
                            rem -= take
                        if rem <= 0 and alloc:
                            p = planets[j]
                            val = p[6] * PROD_W + (NEUTRAL_BONUS if p[1] == -1
                                                   else ENEMY_BONUS)
                            if any(o == me for (_, _, o) in arrivals[j]):
                                val += COMMIT_BONUS
                            score = val / (need + 12.0) * 100.0 - T * TIME_W
                            return (score, T, alloc)
                        break
                    T += 1
            return None

        opened = 0
        while opened < MAX_PLANS and len(self.plans) < MAX_ACTIVE_PLANS:
            if time.monotonic() > deadline:
                break
            avail_src = [i for i in mine if i not in launched and free(i) >= MIN_FLEET]
            if not avail_src:
                break
            best = None
            best_j = None
            for j in shortlist:
                if planets[j][0] in self.plans:
                    continue
                if time.monotonic() > deadline:
                    break
                pl = plan_target(j, avail_src)
                if pl and (best is None or pl[0] > best[0]):
                    best = pl
                    best_j = j
            if best is None:
                break
            score, T, alloc = best
            self.plans[planets[best_j][0]] = {
                "arrive": step + T,
                "alloc": alloc,
                "sent": set(),
                "opened": step,
            }
            for sid, cnt in alloc.items():
                si = world.idx.get(sid)
                if si in reserved:
                    reserved[si] += cnt
            opened += 1
            if _dbg is not None and len(alloc) > 1:
                _dbg.write("P%d T%-4d PLAN target=%d arrive=%d pooled=%d alloc=%s\n"
                           % (me, step, planets[best_j][0], step + T, len(alloc),
                              dict(alloc)))

        # Fire whichever contributors of the freshly opened plans are due now.
        for tid, pl in self.plans.items():
            j = world.idx.get(tid)
            if j is None:
                continue
            rem = pl["arrive"] - step
            if rem < 1 or rem > world.H:
                continue
            for sid in list(pl["alloc"].keys()):
                if sid in pl["sent"]:
                    continue
                i = world.idx.get(sid)
                if i is None or i in launched or i not in v_ships:
                    continue
                want = min(pl["alloc"][sid], v_ships[i])
                if want < MIN_FLEET or v_energy[i] < LAUNCH_COST:
                    continue
                k, ax, ay = world.arrival(i, j, want)
                if k != rem:
                    continue
                hit, tick = world.simulate_launch(i, want, ax, ay)
                if hit != j or tick != rem:
                    continue
                if commit(i, ax, ay, want):
                    pl["sent"].add(sid)
                    reserved[i] = max(0, reserved.get(i, 0) - pl["alloc"][sid])

        # --------------------------------------------------------------
        # PHASE 3 -- Economic hub logistics.
        # --------------------------------------------------------------
        if mine and enemy_ids and time.monotonic() <= deadline:
            front = min(enemy_dist.values())
            staging = [i for i in mine if enemy_dist[i] <= front * 1.15]
            for i in mine:
                if i in launched or v_energy[i] < LAUNCH_COST or i in compromised:
                    continue
                surplus = free(i)
                if surplus < HUB_MIN_FLEET:
                    continue
                if enemy_dist[i] < front * HUB_GAIN:
                    continue                          # already frontline; hold
                best_dst = None
                best_k = None
                for j in staging:
                    if j == i or owners[j][min(world.H, 12)] != me:
                        continue
                    k, ax, ay = world.arrival(i, j, surplus)
                    if k > world.H - 4:
                        continue
                    if not sun_path_clear(planets[i][2], planets[i][3], ax, ay):
                        continue
                    if best_k is None or k < best_k:
                        best_k = k
                        best_dst = (j, ax, ay)
                if best_dst is None:
                    continue
                j, ax, ay = best_dst
                hit, _ = world.simulate_launch(i, surplus, ax, ay)
                if hit == j:
                    commit(i, ax, ay, surplus)

        if _dbg is not None:
            res_tot = sum(reserved.values())
            stale = sum(1 for pl in self.plans.values() if not pl["sent"])
            _dbg.write(
                "P%d S%-4d mine=%-3d plans=%-2d unstarted=%d reserved=%-6d "
                "acts=%d ships=%d\n"
                % (me, step, len(mine), len(self.plans), stale, res_tot,
                   len(actions), sum(v_ships.values())))
        return actions


def main():
    cmd = Commander()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        deadline = time.monotonic() + TIME_BUDGET
        try:
            obs = json.loads(line)
            out = cmd.act(obs, deadline)
        except Exception:
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
            out = []
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
