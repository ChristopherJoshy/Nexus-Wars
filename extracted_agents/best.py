import json
import math
import os
import sys
import time
import traceback

BOARD = 100.0
C = 50.0
SUN_R = 10.0
ROT_LIMIT = 50.0
MAX_SPEED = 6.0
LAUNCH_COST = 20
LAUNCH_OFFSET = 0.1

SUN_PAD = 1.8
HORIZON = 60
HORIZON_MIN = 26
WORK_BUDGET = 90000
TIME_BUDGET = 0.12
MAX_POOL = 8
MAX_PLANS = 4
MAX_TARGETS = 18
TOT_WINDOW = 8
BASE_KEEP = 2
ENERGY_CYCLE = 80.0
EXPAND_W = 1.0
IMMEDIATE_CAPTURE = True
HUB_LOGISTICS = False
PROD_EXP = 1.0
FRONT_KEEP = 8
FRONT_DIST = 30.0
MIN_FLEET = 3
HUB_MIN_FLEET = 10
HUB_GAIN = 1.15
CAPACITY_SAFETY = 1.00
PROD_W = 26.0
NEUTRAL_BONUS = 34.0
ENEMY_BONUS = 20.0
TIME_W = 1.35
COMMIT_BONUS = 45.0
LANE_GAIN = 1.25
LANE_TIME_W = 1.0
AIM_OFFSETS = (0.015, -0.015, 0.03, -0.03, 0.05, -0.05)
RECOVERY_BUDGET = 40
MAX_ACTIVE_PLANS = 6
PLAN_STALE = 10
DIFF_KEEP_RELAX = 0.40
DIFF_EXPAND_BONUS = 55.0
DIFF_URGENT = -2
MULTI_LAUNCH = 1

_SPEED_CACHE = {}


def debug_log(msg):
    try:
        sys.stderr.write("[best] %s\n" % (msg,))
        sys.stderr.flush()
    except Exception:
        pass


def _finite(*vals):
    for v in vals:
        if not isinstance(v, (int, float)):
            return False
        if v != v or v == float("inf") or v == float("-inf"):
            return False
    return True


def sanitize(obs):
    planets = []
    for p in obs.get("planets") or []:
        if not isinstance(p, (list, tuple)) or len(p) < 10:
            continue
        if not _finite(p[2], p[3], p[4], p[5], p[6], p[7], p[9]):
            continue
        if p[4] <= 0.0:
            continue
        regen = float(p[9]) if p[9] and p[9] > 0 else 1.0
        planets.append([p[0], int(p[1]), float(p[2]), float(p[3]), float(p[4]),
                        int(p[5]), int(p[6]), float(p[7]), float(p[8]), regen])
    fleets = []
    for f in obs.get("fleets") or []:
        if not isinstance(f, (list, tuple)) or len(f) < 8:
            continue
        if not _finite(f[2], f[3], f[4], f[6]):
            continue
        if int(f[6]) <= 0:
            continue
        fleets.append([f[0], int(f[1]), float(f[2]), float(f[3]), float(f[4]),
                       f[5], int(f[6]), f[7]])
    av = obs.get("angular_velocity", 0.035)
    if not _finite(av):
        av = 0.035
    return planets, fleets, float(av)


def fleet_speed(ships):
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
    def __init__(self, planets, fleets, av, me):
        self.me = me
        self.av = av
        self.planets = planets
        self.fleets = fleets
        self.n = len(self.planets)
        self.idx = {p[0]: i for i, p in enumerate(self.planets)}
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
            self.rotates.append(r + p[4] < ROT_LIMIT)
        self._build_positions()
        self._k_cache = {}

    def _build_positions(self):
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

    def intercept(self, sx, sy, r_src, j, v):
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
        v = fleet_speed(ships)
        key = (i, j, int(v * 20.0))
        got = self._k_cache.get(key)
        if got is None:
            p = self.planets[i]
            got = self.intercept(p[2], p[3], self.radius[i], j, v)
            self._k_cache[key] = got
        return got

    def simulate_launch(self, i, ships, aim_x, aim_y):
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

    def simulate_arrivals(self):
        n = self.n
        rad = self.radius
        orb = self.orb_r
        arrivals = [[] for _ in range(n)]
        for f in self.fleets:
            ships = f[6]
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


def aim_candidates(world, i, j, ships):
    p = world.planets[i]
    k, ax, ay = world.arrival(i, j, ships)
    out = []
    if sun_path_clear(p[2], p[3], ax, ay):
        out.append((ax, ay))
    dx = ax - p[2]
    dy = ay - p[3]
    D = math.hypot(dx, dy)
    if D <= 1e-9:
        return out
    base = math.atan2(dy, dx)
    for dth in AIM_OFFSETS:
        cx = p[2] + D * math.cos(base + dth)
        cy = p[3] + D * math.sin(base + dth)
        if sun_path_clear(p[2], p[3], cx, cy):
            out.append((cx, cy))
    return out


def build_threat_matrix(world, owners, ships):
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
    def __init__(self):
        self.plans = {}
        self.turn = 0

    def _prune(self, world, owners, step):
        me = world.me
        for tid in list(self.plans.keys()):
            pl = self.plans[tid]
            j = world.idx.get(tid)
            if j is None or pl["arrive"] <= step:
                del self.plans[tid]
                continue
            if not pl["sent"] and step - pl["opened"] > PLAN_STALE:
                del self.plans[tid]
                continue
            rem = pl["arrive"] - step
            if rem <= world.H and owners[j][rem] == me and not pl["sent"]:
                del self.plans[tid]
                continue
            for sid in list(pl["alloc"].keys()):
                si = world.idx.get(sid)
                if si is None or world.planets[si][1] != me:
                    pl["alloc"].pop(sid, None)
                    pl["sent"].discard(sid)
            if not pl["alloc"]:
                del self.plans[tid]

    def act(self, obs, deadline):
        me = obs.get("player", 0)
        planets_in, fleets_in, av = sanitize(obs)
        if not planets_in:
            return []
        world = World(planets_in, fleets_in, av, me)
        n = world.n
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

        planet_diff = len(mine) - len(enemy_ids)
        behind = planet_diff < 0
        urgent = planet_diff <= DIFF_URGENT
        keep_scale = DIFF_KEEP_RELAX if urgent else (0.65 if behind else 1.0)
        expand_bonus = DIFF_EXPAND_BONUS if behind else 0.0

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
            if keep_scale < 1.0:
                spec = k - max(0, inc_e - inc_f)
                k = max(0, inc_e - inc_f) + spec * keep_scale
            keep[i] = min(int(k), planets[i][5])

        reserved = {i: 0 for i in mine}
        for pl in self.plans.values():
            for sid, cnt in pl["alloc"].items():
                if sid in pl["sent"]:
                    continue
                si = world.idx.get(sid)
                if si in reserved:
                    reserved[si] += cnt
        for i in mine:
            spendable = max(0, v_ships[i] - keep[i])
            if reserved[i] > spendable:
                reserved[i] = spendable

        def free(i):
            return v_ships[i] - keep[i] - reserved.get(i, 0)

        _recovery_budget = [RECOVERY_BUDGET]

        def clean_shot(i, j, ships, want_tick=None, max_tick=None):
            cands = aim_candidates(world, i, j, ships)
            for idx, (cx, cy) in enumerate(cands):
                if idx > 0:
                    if _recovery_budget[0] <= 0:
                        return None
                    _recovery_budget[0] -= 1
                hit, tick = world.simulate_launch(i, ships, cx, cy)
                if hit != j:
                    continue
                if want_tick is not None and tick != want_tick:
                    continue
                if max_tick is not None and tick > max_tick:
                    continue
                return cx, cy, tick
            return None

        def commit(i, aim_x, aim_y, ships):
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
                    send = avail
                    k2, ax2, ay2 = world.arrival(i, j, send)
                    if k2 > crit:
                        continue
                shot = clean_shot(i, j, send, max_tick=crit)
                if shot is None:
                    continue
                ax2, ay2, _ = shot
                if commit(i, ax2, ay2, send):
                    need -= send
                    reserved[i] = 0

        if time.monotonic() > deadline:
            return actions

        if time.monotonic() > deadline:
            return actions

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
                    continue
                if k > rem:
                    boost = min(v_ships[i] - keep[i], v_ships[i])
                    if boost > want:
                        k2, ax2, ay2 = world.arrival(i, j, boost)
                        if k2 == rem:
                            want, k, ax, ay = boost, k2, ax2, ay2
                    if k > rem:
                        continue
                shot = clean_shot(i, j, want, want_tick=rem)
                if shot is None:
                    continue
                ax, ay, _ = shot
                if commit(i, ax, ay, want):
                    pl["sent"].add(sid)
                    reserved[i] = max(0, reserved.get(i, 0) - pl["alloc"][sid])

        if time.monotonic() > deadline:
            return actions

        my_cx = sum(planets[i][2] for i in mine) / len(mine)
        my_cy = sum(planets[i][3] for i in mine) / len(mine)
        shortlist = []
        for j in range(n):
            if planets[j][1] == me or planets[j][0] in self.plans:
                continue
            p = planets[j]
            d = math.hypot(p[2] - my_cx, p[3] - my_cy)
            val = ((p[6] ** PROD_EXP) * PROD_W +
                   (NEUTRAL_BONUS + expand_bonus if p[1] == -1 else ENEMY_BONUS))
            inbound = any(o == me for (_, _, o) in arrivals[j])
            cheapest = p[5]
            for t in range(1, world.H + 1):
                if owners[j][t] == me:
                    break
                g = proj[j][t]
                if g < cheapest:
                    cheapest = g
            shortlist.append((-(val - d * 0.9 - cheapest * 0.30 +
                                (COMMIT_BONUS if inbound else 0.0)), j))
        shortlist.sort()
        shortlist = [j for _, j in shortlist[:MAX_TARGETS]]

        def demand(j, T):
            if owners[j][T] == me:
                return -1
            g = proj[j][T]
            return g + 2 + int(g * 0.02)

        def plan_target(j, avail_src):
            cands = []
            for i in avail_src:
                cap = free(i)
                if cap < MIN_FLEET:
                    continue
                k, ax, ay = world.arrival(i, j, cap)
                if k > world.H - 4:
                    continue
                if not aim_candidates(world, i, j, cap):
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
                    static_tgt = planets[j][1] == -1
                    supply = []
                    total = 0
                    for i in subset:
                        cap = free(i)
                        if cap < MIN_FLEET:
                            continue
                        k, _, _ = world.arrival(i, j, cap)
                        if k > T:
                            continue
                        d = T - k
                        if v_energy[i] + planets[i][9] * d < LAUNCH_COST:
                            continue
                        if static_tgt and d > 0:
                            cap += planets[i][6] * d
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
                                take = int(cap)
                                k2, _, _ = world.arrival(i, j, take)
                                if k2 > T:
                                    continue
                            alloc[planets[i][0]] = take
                            rem -= take
                        if rem <= 0 and alloc:
                            p = planets[j]
                            val = ((p[6] ** PROD_EXP) * PROD_W +
                                   (NEUTRAL_BONUS + expand_bonus if p[1] == -1
                                    else ENEMY_BONUS))
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
                shot = clean_shot(i, j, want, want_tick=rem)
                if shot is None:
                    continue
                ax, ay, _ = shot
                if commit(i, ax, ay, want):
                    pl["sent"].add(sid)
                    reserved[i] = max(0, reserved.get(i, 0) - pl["alloc"][sid])

        claimed = set()

        def svt_solve(i, j, budget):
            s_try = budget
            for _ in range(5):
                k, ax, ay = world.arrival(i, j, s_try)
                if k > world.H - 4:
                    return None
                nd = demand(j, k)
                if nd < 0 or nd > budget:
                    return None
                if nd == s_try:
                    return nd, k
                s_try = nd
            return (s_try, k) if s_try <= budget else None

        for i in (mine if IMMEDIATE_CAPTURE else ()):
            if i in launched or v_energy[i] < LAUNCH_COST:
                continue
            skip = set()
            for _ in range(MULTI_LAUNCH):
                if v_energy[i] < LAUNCH_COST:
                    break
                avail_now = free(i)
                if avail_now < MIN_FLEET:
                    break
                best = None
                for j in shortlist:
                    if j in claimed or j in skip or planets[j][0] in self.plans:
                        continue
                    sol = svt_solve(i, j, avail_now)
                    if sol is None:
                        continue
                    ships, k = sol
                    if ships < MIN_FLEET:
                        ships = MIN_FLEET
                    q = planets[j]
                    val = ((q[6] ** PROD_EXP) * PROD_W +
                           (NEUTRAL_BONUS + expand_bonus if q[1] == -1 else ENEMY_BONUS))
                    score = val / (ships + 8.0) * 100.0 * EXPAND_W - k * TIME_W
                    if best is None or score > best[0]:
                        best = (score, j, ships, k)
                if best is None:
                    break
                _, j, ships, k = best
                shot = clean_shot(i, j, ships, want_tick=k)
                if shot is None:
                    skip.add(j)
                    continue
                ax, ay, tick = shot
                if not commit(i, ax, ay, ships):
                    break
                claimed.add(j)

        if time.monotonic() > deadline:
            return actions

        if HUB_LOGISTICS and enemy_ids and time.monotonic() <= deadline:

            def tgt_val(j):
                q = planets[j]
                return (q[6] ** PROD_EXP) * PROD_W + (NEUTRAL_BONUS if q[1] == -1 else ENEMY_BONUS)

            lane = {}
            for i in mine:
                acc = 0.0
                cap = max(free(i), MIN_FLEET)
                for j in shortlist:
                    k, ax, ay = world.arrival(i, j, cap)
                    if k > world.H - 4:
                        continue
                    if not sun_path_clear(planets[i][2], planets[i][3], ax, ay):
                        continue
                    acc += tgt_val(j) / (k + 6.0)
                lane[i] = acc

            for i in mine:
                if i in launched or v_energy[i] < LAUNCH_COST or i in compromised:
                    continue
                surplus = free(i)
                if surplus < HUB_MIN_FLEET:
                    continue
                bar = lane[i] * LANE_GAIN
                best = None
                for j in mine:
                    if j == i or lane[j] < bar:
                        continue
                    if owners[j][min(world.H, 12)] != me:
                        continue
                    k, ax, ay = world.arrival(i, j, surplus)
                    if k > world.H - 4:
                        continue
                    sc = lane[j] - k * LANE_TIME_W
                    if best is None or sc > best[0]:
                        direct = sun_path_clear(planets[i][2], planets[i][3], ax, ay)
                        best = (sc, j, ax, ay, direct)
                if best is None:
                    continue
                _, j, ax, ay, direct = best
                if direct:
                    hit, _ = world.simulate_launch(i, surplus, ax, ay)
                    if hit == j and commit(i, ax, ay, surplus):
                        continue
                rel = get_best_relay(world, i, j, surplus, mine)
                if rel:
                    r, rx, ry = rel
                    rhit, _ = world.simulate_launch(i, surplus, rx, ry)
                    if rhit == r:
                        commit(i, rx, ry, surplus)

        return actions


def main():
    cmd = Commander()
    for line in sys.stdin:
        try:
            line = line.strip()
            if not line:
                continue
            deadline = time.monotonic() + TIME_BUDGET
            obs = json.loads(line)
            if not isinstance(obs, dict):
                raise ValueError("observation is not a JSON object")
            out = cmd.act(obs, deadline)
            if not isinstance(out, list):
                out = []
        except Exception:
            out = []
        try:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
        except Exception:
            return


if __name__ == "__main__":
    main()
