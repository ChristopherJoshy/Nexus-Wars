#!/usr/bin/env python3
"""
AbominationUltra - Nexus Wars agent.

Built from ladder telemetry (31 matches, 15,876 reconstructed launches).  The
kinematic core is carried over from jatayu_v1 and is verified exact against the
shipped interpreter; what is new is the ECONOMY OF TEMPO, which the data says
decides these games.

WHAT THE TELEMETRY SAID
-----------------------
  * Production at step 50 predicts the winner in 83% of ladder matches
    (winners avg 21.2 production, losers 12.6).  Launch count through step 120
    is the single strongest correlate of victory, r = +0.573.
  * 67-78% of all owned-planet-steps sit pinned at the 100 energy cap, bleeding
    5 regen/step into vacuum.  Energy is therefore NOT the binding constraint --
    decisions are.  Cadence, not hoarding, wins.
  * Opening moves are ~99% aimed at neutrals.  The strong ladder bots open on
    production-3.3 planets with ~9-ship fleets; jatayu_v1 opened on
    production-2.6 planets with ~15-ship fleets, i.e. slower and worse-aimed.
  * Autopsy of the one identified ladder loss (seed 2135124292): jatayu_v1
    launched 4 times in the first 60 steps against the opponent's 25, and was
    dead by step 150.  Reproduced locally at 5 launches / production 9.

THE BUG THAT COST THE MATCH
---------------------------
jatayu_v1 routed EVERY capture through the Time-on-Target planner, including
single-fleet captures.  A ToT plan reserves ships and then waits for its
contributor's flight time k to equal the plan's remaining time -- but a lone
fleet has nothing to synchronise with.  On that map it opened a plan reserving
12 ships while holding 10, sat 20 turns with zero actions while the reservation
blocked every other use, and by step 10 held two phantom plans reserving 24
ships it did not own.  The opponent took its first planet on step 6.

AbominationUltra fixes this structurally:
  * IMMEDIATE CAPTURE.  Any planet that can take a target by itself launches
    this turn.  Synchronisation is applied only where it buys something --
    strikes needing two or more contributors.
  * NO PHANTOM RESERVATIONS.  A plan may never reserve ships that are not
    actually held, so one stalled plan can no longer freeze the whole economy.
  * ZERO-WASTE ENERGY.  A planet at/near the cap with spendable ships is
    required to convert that energy into territory rather than idle at 100.

RETAINED DOCTRINE
-----------------
  * Threat Matrix first: every airborne fleet is ray-cast and every friendly
    garrison simulated forward; planets projected to fall get a timed
    reinforcement before any offensive ship is spent.
  * Synchronized Time-on-Target swarming for garrisons no single planet can
    break.  The engine SUMS same-tick arrivals of one player, so pooled fleets
    fight as one stack; contributors launch staggered so all land together.
  * Dynamic economic hubs, routed by firing lane, with thermodynamic relay
    bypass around the Sun.
  * Capital preservation: a launch is committed only when the arrival strictly
    overwhelms the projected garrison (ties revert the planet to neutral), and
    every launch is replayed through engine rules before it is issued.

ENGINE-EXACTNESS (measured, not assumed)
----------------------------------------
  * Arrival tick k = ceil((|P(t*) - src_c| - r_src - 0.1 - r_tgt) / v).  The
    engine spawns fleets at r_src + 0.1 and scores a hit once the swept segment
    comes within r_tgt of the target centre.  Exact on 15/15 controlled cases.
  * Orbital phase: the observation at step S holds angle init + av*(S-1), so a
    fleet flying k ticks meets the planet at init + av*(S-1+k) -- lead the
    OBSERVED position by av*k.  Orbital radius is rotation-invariant.
  * swept_hit reproduces the interpreter's swept-pair quadratic discriminant
    test exactly, including its root-interval check and first-hit-wins order.
    No integer-step ray-casting, so fast fleets cannot tunnel.
  * obs["step"] is NOT trustworthy -- the harness sets observation.step for
    player 0 only, so seat 1 reads 0 all match.  We keep our own clock.
  * Measured shot quality: 90.7% of shots land, 98.7% on the exact tick.

BUDGET: stdlib only.  numpy is available on the ladder but deliberately unused:
importing it costs 554 ms cold / 134 ms warm, and while the ladder allows
1000 ms/turn, the local harness enforces 150 ms -- this engine runs in ~9 ms
worst case, so numpy would buy nothing and risk a first-turn kill.
"""



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
TIME_BUDGET = 0.12           # safe under BOTH the 1000 ms ladder and a 150 ms harness
MAX_POOL = 8                 # max planets pooled into one ToT strike
MAX_PLANS = 4                # max NEW strikes opened per turn
MAX_TARGETS = 18             # target shortlist size
TOT_WINDOW = 8               # extra arrival ticks probed past the earliest
BASE_KEEP = 2                # baseline garrison never spent
ENERGY_CYCLE = 80.0          # above this, idle energy is being burned
EXPAND_W = 1.0               # weight on production-per-ship when expanding
IMMEDIATE_CAPTURE = True     # zero-waste backstop (see PHASE 2d)
HUB_LOGISTICS = False        # OFF by measurement.  The ship audit showed 74-81%
                             # of all launched ships were internal shuffling, at
                             # 20 energy a hop -- and ToT pooling already
                             # converges fleets on a target without pre-staging
                             # them, so the staging was largely redundant.
                             # Direct A/B: 67-53 (56%) over 120 games with it off.
PROD_EXP = 1.0               # linear: superlinear tested at 48% vs 50%, no gain
FRONT_KEEP = 8               # extra garrison held on frontline planets
FRONT_DIST = 30.0            # "frontline" = this close to an enemy planet
MIN_FLEET = 3
HUB_MIN_FLEET = 10           # a logistics run must be worth its 20 energy
HUB_GAIN = 1.15              # rear planet must be this much further out
CAPACITY_SAFETY = 1.00       # `need` already carries its own +2 capture margin
PROD_W = 26.0
NEUTRAL_BONUS = 34.0
ENEMY_BONUS = 20.0
TIME_W = 1.35
COMMIT_BONUS = 45.0          # bias toward targets we already committed to
LANE_GAIN = 1.25             # destination must be this much better a firing seat
LANE_TIME_W = 1.0            # discount on staging flight time
AIM_OFFSETS = (0.015, -0.015, 0.03, -0.03, 0.05, -0.05)   # radians
RECOVERY_BUDGET = 40         # max re-aim simulations per turn
MAX_ACTIVE_PLANS = 6         # cap on simultaneously open ToT plans
PLAN_STALE = 10              # drop an unstarted plan after this many turns

_SPEED_CACHE = {}


def debug_log(msg):
    """Diagnostics to stderr only, flushed immediately.

    Never touches stdout: stdout is the action channel, and a stray byte there
    desynchronises the line protocol and kills the agent.
    """
    try:
        sys.stderr.write("[jatayu] %s\n" % (msg,))
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
    """Defensive parse -- assume the engine can hand us truncated or junk data.

    Planets need indices 0..9, fleets 0..7.  Anything short, non-numeric,
    non-finite, or with a non-positive radius is dropped rather than trusted.
    Relative order of surviving planets is preserved, because the engine
    resolves a fleet against the FIRST planet in list order that it touches.
    """
    planets = []
    for p in obs.get("planets") or []:
        if not isinstance(p, (list, tuple)) or len(p) < 10:
            continue
        if not _finite(p[2], p[3], p[4], p[5], p[6], p[7], p[9]):
            continue
        if p[4] <= 0.0:
            continue
        regen = float(p[9]) if p[9] and p[9] > 0 else 1.0   # no zero division
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

    def __init__(self, planets, fleets, av, me):
        self.me = me
        self.av = av
        self.planets = planets
        self.fleets = fleets
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


def aim_candidates(world, i, j, ships):
    """Aim points to try for i -> j, best first.

    Over half of all firing lanes are unusable (~26% Sun-blocked, ~28%
    absorbed by an intervening planet).  A small angular offset re-routes the
    fleet around the obstruction while still striking the target disc, which
    recovers a meaningful share of them.  Only aims that clear the Sun are
    returned; the caller still replays each through engine rules.
    """
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


class AbominationUltra:
    """Tempo-first commander: immediate capture, ToT only where it pays.

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
        # Reservations are capped at what the planet ACTUALLY holds.  jatayu_v1
        # let a plan reserve ships that did not exist yet, which froze the
        # whole economy behind one stalled plan (see module docstring).
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
            """Resolve an aim that genuinely lands on j under engine rules.

            Tries the direct intercept first, then small angular offsets to
            slip past whatever is fouling the lane.  Returns (ax, ay, tick) or
            None.  Offsets draw on a per-turn budget so re-aiming can never
            blow the timeout.
            """
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
                shot = clean_shot(i, j, send, max_tick=crit)
                if shot is None:
                    continue
                ax2, ay2, _ = shot
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
            val = (p[6] ** PROD_EXP) * PROD_W + (NEUTRAL_BONUS if p[1] == -1 else ENEMY_BONUS)
            inbound = any(o == me for (_, _, o) in arrivals[j])
            # Price the target at its CHEAPEST projected moment, not its price
            # today.  A fat neutral the enemy is about to storm will be left
            # holding a handful of ships (capture sets ships = abs(overkill)),
            # and that is the moment to take it -- they pay for the siege, we
            # take the planet.  Scoring off p[5] hides those windows entirely.
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
            """Ships needed to take planet j on tick T, given all in flight."""
            if owners[j][T] == me:
                return -1
            g = proj[j][T]
            return g + 2 + int(g * 0.02)

        # --------------------------------------------------------------
        # PHASE 2c -- Open Time-on-Target plans for what one planet CANNOT take.
        # --------------------------------------------------------------
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
                if not aim_candidates(world, i, j, cap):
                    continue                     # no lane clears the Sun at all
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
                    # A NEUTRAL garrison is static (neutrals never produce),
                    # so a delayed contributor may be funded by the ships it
                    # will actually hold at its own launch turn.  Against an
                    # OWNED planet the garrison grows, so present ships only --
                    # that asymmetry is what makes early commitment safe here
                    # and reckless there.
                    static_tgt = planets[j][1] == -1
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
                                take = int(cap)       # buy speed with mass
                                k2, _, _ = world.arrival(i, j, take)
                                if k2 > T:
                                    continue
                            alloc[planets[i][0]] = take
                            rem -= take
                        if rem <= 0 and alloc:
                            p = planets[j]
                            val = ((p[6] ** PROD_EXP) * PROD_W +
                                   (NEUTRAL_BONUS if p[1] == -1 else ENEMY_BONUS))
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
                shot = clean_shot(i, j, want, want_tick=rem)
                if shot is None:
                    continue
                ax, ay, _ = shot
                if commit(i, ax, ay, want):
                    pl["sent"].add(sid)
                    reserved[i] = max(0, reserved.get(i, 0) - pl["alloc"][sid])

        # --------------------------------------------------------------
        # PHASE 2d -- IMMEDIATE CAPTURE (zero-waste tempo backstop).
        #
        # Runs AFTER the planner, on planets it left idle.  A lone fleet has
        # nothing to synchronise with, so a planet that can take a target by
        # itself must never sit waiting on an arrival tick -- that stall is
        # exactly what lost seed 2135124292 (4 launches in 60 steps).  Ordering
        # matters: fired before the planner, this out-bids the better pooled
        # captures and costs more tempo than it buys.
        # --------------------------------------------------------------
        claimed = set()

        def svt_solve(i, j, budget):
            """Couple fleet size, speed and flight time to a fixed point.

            Size sets speed, speed sets arrival tick, arrival tick sets the
            garrison we must beat, which sets size.  Returns (ships, k) or None.
            """
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
            avail_now = free(i)
            if avail_now < MIN_FLEET:
                continue
            best = None
            for j in shortlist:
                if j in claimed or planets[j][0] in self.plans:
                    continue
                sol = svt_solve(i, j, avail_now)
                if sol is None:
                    continue
                ships, k = sol
                if ships < MIN_FLEET:
                    ships = MIN_FLEET
                q = planets[j]
                val = (q[6] ** PROD_EXP) * PROD_W + (NEUTRAL_BONUS if q[1] == -1 else ENEMY_BONUS)
                # Production bought per ship burned, discounted by flight time.
                score = val / (ships + 8.0) * 100.0 * EXPAND_W - k * TIME_W
                if best is None or score > best[0]:
                    best = (score, j, ships, k)
            if best is None:
                continue
            _, j, ships, k = best
            shot = clean_shot(i, j, ships, want_tick=k)
            if shot is None:
                continue
            ax, ay, tick = shot
            if commit(i, ax, ay, ships):
                claimed.add(j)

        if time.monotonic() > deadline:
            return actions

        # --------------------------------------------------------------
        # PHASE 3 -- Dynamic economic hubs, routed by FIRING LANE.
        #
        # Over half of all source->target lanes are unusable: ~26% are blocked
        # by the Sun and ~28% are absorbed by an intervening planet.  So a
        # planet's worth is not its distance to the enemy -- it is how much
        # target value it can actually shoot at.  Surplus therefore migrates
        # toward the best firing seats, relaying around the Sun when the
        # direct lane is fouled.
        # --------------------------------------------------------------
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
                bar = lane[i] * LANE_GAIN        # strict improvement kills cycles
                best = None
                for j in mine:
                    if j == i or lane[j] < bar:
                        continue
                    if owners[j][min(world.H, 12)] != me:
                        continue                 # destination is not going to hold
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
                # Direct lane fouled: bypass the Sun through a friendly node,
                # costed with its energy-regeneration delay.
                rel = get_best_relay(world, i, j, surplus, mine)
                if rel:
                    r, rx, ry = rel
                    rhit, _ = world.simulate_launch(i, surplus, rx, ry)
                    if rhit == r:
                        commit(i, rx, ry, surplus)

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
    """Line protocol: one observation in, one action array out, always."""
    cmd = AbominationUltra()
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
            # A silent [] here once masked a live NameError for a whole match.
            msg = "turn fault -- emitting empty action\n" + traceback.format_exc()
            debug_log(msg)
            if _dbg is not None:
                _dbg.write(msg + "\n")
            out = []
        try:
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
        except Exception:
            debug_log("stdout closed\n" + traceback.format_exc())
            return


if __name__ == "__main__":
    main()
