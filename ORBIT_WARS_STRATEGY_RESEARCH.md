**Status**: success
**Summary**: Researched 6+ open-source Orbit Wars bots and strategy documents; compiled concrete, implementable strategies for a Python agent.

---

## Orbit Wars / Nexus Wars — Competitive Strategy Research Report

### 1. Game Mechanics (from engine source)

**Planet tuple**: `[id, owner, x, y, radius, ships, production]`
- Production per turn = `planet[6]` (1-5)
- Starting ships on home planets = 10
- Neutral planets have 5-30 ships (random), owned by -1

**Fleet tuple**: `[id, owner, x, y, angle, from_planet_id, ships]`
- Speed formula: `1.0 + 5.0 * (log10(ships) / log10(1000)) ** 1.5`, capped at 6.0
- 1 ship = speed 1.0, 1000 ships ≈ speed 6.0 max
- Fleets destroyed if they cross within SUN_RADIUS (10.0) of center (50, 50)
- Combat: largest fleet survives, attacker's surplus ships subtract from defender. If attacker wins, planet flips. Ties kill both.

**Comets**: Spawn at turns 50, 150, 250, 350, 450. Production = 1. Expire after path runs out.

**EPISODE_STEPS** = 500. Score = total ships owned (planets + fleets) at end.

**Map**: 100×100 board, 4-fold rotational symmetry. Static planets (orbital_r + r ≥ 50) don't orbit. Orbiting planets rotate at `angular_velocity` (0.025-0.05 rad/turn).

**Angular velocity** is uniform across the map. Use `obs.angular_velocity`.

---

### 2. Kaggle Starter Bot — Full Code & Weaknesses

The starter bot (`starter_agent` in `orbit_wars.py`) does only ONE thing:
```python
for mp in my_planets:
    if mp.ships <= 0: continue
    closest = None; min_dist = float('inf')
    for t in static_targets: # only static planets (orbital_r + r >= 50)
        dist = math.hypot(mp.x - t.x, mp.y - t.y)
        if dist < min_dist: min_dist = dist; closest = t
    if closest:
        angle = math.atan2(closest.y - mp.y, closest.x - mp.x)
        ships = mp.ships // 2  # sends HALF, even if that's 2 ships
        if ships >= 20:        # only fires with 20+ ships (40 ships on planet minimum!)
            moves.append([mp.id, angle, ships])
```

**Critical Weaknesses to Exploit**:

| # | Weakness | Exploitation Strategy |
|---|---|---|
| 1 | **Only attacks static planets** | The starter bot completely ignores orbiting planets — they are free captures for your bot. Rush orbiting (non-static) neutrals early — the starter will never contest them. |
| 2 | **Min 20-ship threshold** | Only fires if remaining garrison after sending half is ≥ 20 (i.e. planet needs ≥40 ships). A planet with 39 ships does nothing. Your bot can send even 3-ship fleets. |
| 3 | **Sends exactly half every time** | Fixed fraction = no phase awareness. Early game this is way too conservative. Late game this is way too stingy. |
| 4 | **No defense at all** | Zero fleet-intercept logic, zero reaction to incoming threats. Attack any starter planet with impunity — it won't reinforce. |
| 5 | **No orbital prediction** | Aims at current position. Orbiting targets move by the time fleet arrives. Your bot can hit them because it predicts. |
| 6 | **No multi-source coordination** | Every planet independently picks its closest static target. Multiple planets may attack the same target redundantly while leaving others untouched. |
| 7 | **No sun avoidance checking** | Fires straight-line. Fleets flying through the sun are destroyed silently. |
| 8 | **No comet awareness** | Ignores comets entirely, even though they're free planets with low ship counts. |
| 9 | **No endgame push** | Plays the same strategy on turn 499 as turn 1. A bot that switches to "suicide all ships" in the last 40 turns will massively outscore it on ship count. |
| 10 | **Fails in FFA** | Same strategy regardless of opponent count. No sandbagging, no leader targeting, no elimination focus. |

**vs Starter Bot expected win rate for a competent bot**: ~70-85% based on ORACLE benchmarks (83.3% over 30 seeds, 57.5% for "baseline" vs starter).

---

### 3. Top 5 Most Impactful Strategies

These are ordered from lowest implementation effort to highest payoff.

#### Strategy 1: Phase-Aware Expansion → Consolidation → Endgame Rush

**Source**: juandalfonso v11 bot (score 431), comet_reaper terminal phase config

**Concept**: The game has distinct phases that demand different behaviors. A simple state machine with 3 states dramatically outperforms single-strategy bots.

| Phase | When | Behavior | Parameters |
|---|---|---|---|
| **Expansion** | Early (planets < threshold) | Capture orbiting neutrals aggressively | `min_defense=2`, `max_frac=0.90`, no duplicate targets |
| **Consolidation** | Mid-game (planets ≥ threshold) | Attack enemy planets, regroup | `min_defense=6`, `max_frac=0.65`, one target per source |
| **Endgame Rush ("Suicide Surge")** | Last 40 turns | Fling everything at any planet | `min_defense=1`, `max_frac=0.95`, ignore regroup |

**Implementation**: ~30 lines of Python. Track `len(my_planets)` vs threshold. Last 40 turns → override all safety checks.

**juandalfonso's threshold adaptation** (proven in local testing):
```python
def get_expansion_threshold(num_enemies):
    return {1: 8, 2: 6, 3: 4}.get(num_enemies, 4)
```

**Endgame surge timing**: `if step >= 460: roi_threshold = 1.0, max_waves = 9, enable_regroup = False`

#### Strategy 2: Static-Planet-First Land Grab

**Source**: schmeekler bot (beat comet_reaper 72% in 2P, 35% in 4P)

**Concept**: Static planets (orbital_radius + radius ≥ 50) sit at the periphery, don't rotate, can't drift into enemy territory. They are the "safe" land-grab. Prioritize them for early expansion.

**Implementation**: Add a scoring bonus of **1.5** (empirically tuned) to static planet targets during the expansion phase:
```python
ox = planet[2] - 50.0; oy = planet[3] - 50.0
is_static = math.hypot(ox, oy) + planet[4] >= 49.999
if is_static: score += 1.5  # additive bonus, NOT multiplicative
```

**Key findings**:
- Bonus of 1.5 → beats engine 72% 2P (sweet spot)
- Bonus ≥ 2.0 → overcommits and tanks (too aggressive)
- Bonus works because the flow scorer undervalues static planets (they have no special weight in the engine)

**Limitation**: The #1 bot (1793 Elo) already uses engine variants that account for this. Expected gain: +50-80 Elo vs engine-agnostic bots.

#### Strategy 3: Sun-Aware Orbital Intercept (6-iteration prediction)

**Source**: juandalfonso v5.1 bot, ORACLE bot, all competitive bots

**Concept**: Predict where a target planet will be when your fleet arrives, accounting for orbital motion. Also check the line segment from source to predicted impact point doesn't cross the sun.

**Implementation** (6-iteration fixed point, from juandalfonso):
```python
def aim_angle(src, tgt, ships, ang_vel):
    turns = dist(src, tgt) / fleet_speed(ships)
    fx, fy = tgt.x, tgt.y
    for _ in range(6):
        # predict target position at turns from now
        dx, dy = fx - 50.0, fy - 50.0
        r = math.hypot(dx, dy)
        theta = math.atan2(dy, dx) + ang_vel * turns
        fx = 50.0 + r * math.cos(theta)
        fy = 50.0 + r * math.sin(theta)
        turns = math.hypot(src.x - fx, src.y - fy) / fleet_speed(ships)
    # Sun-crossing check
    if segment_crosses_sun(src.x, src.y, fx, fy):
        return None, None, None  # fall back to no attack
    angle = math.atan2(fy - src.y, fx - src.x)
    return angle, fx, fy
```

**Sun segment check**:
```python
def segment_crosses_sun(ax, ay, bx, by):
    """Returns True if line segment A-B crosses within SUN_RADIUS of center."""
    abx, aby = bx - ax, by - ay
    ab2 = abx*abx + aby*aby
    if ab2 == 0: return math.hypot(50.0 - ax, 50.0 - ay) <= 10.0
    t = max(0.0, min(1.0, ((50.0 - ax)*abx + (50.0 - ay)*aby) / ab2))
    return math.hypot(50.0 - (ax + t*abx), 50.0 - (ay + t*aby)) <= 10.0 + 0.5
```

**Why this matters**: Without orbital prediction, a fleet aimed at a moving planet's current position may miss by 5-15 units by the time it arrives (planets move ~0.03 rad/turn × 50 radius × 20 turns = 30 units). This is the difference between a successful capture and a whiff.

**Performance note**: 6 iterations is fast (~0.01ms per call). Even calling this for 20 planets × 30 targets = 600 times per turn is well under budget.

#### Strategy 4: Fleet-size Calculation ─ Required Ships with ETA Awareness

**Source**: comet_reaper / orbit_lite `capture_floor`, juandalfonso v11 `required_ships`

**Concept**: Don't just send "half" or a fixed number. Calculate exactly how many ships are needed to capture the target, accounting for:
1. Target's current garrison
2. Production the target will accumulate during fleet flight time
3. ETA-dependent reinforcement risk (enemy planets that can reach target before your fleet)

**Simple version** (juandalfonso):
```python
def required_ships(target):
    base = target.ships + 1  # need 1 more than defender
    if target.owner == -1:
        return base            # neutrals: just beat the garrison
    return base + 6            # enemy: +6 buffer (their production during flight)
```

**Better version** (capture floor with reinforcement):
```python
def required_ships(src, tgt, my_planets, ang_vel):
    """Calculate ships needed to capture tgt from src."""
    turns = compute_eta(src, tgt, ang_vel)  # integer turns
    needed = tgt.ships + 1  # beat current garrison
    
    # Account for target's production during flight
    needed += tgt.production * max(0, turns - 2)  # production starts after first tick
    
    # Buffer for enemy reinforcement reachable within flight time
    for ep in enemy_planets_near(tgt, turns):
        needed += min(ep.ships * 0.3, 15)  # fraction of nearby enemy supply
    
    # Don't send more than source can spare (keep reserve)
    reserve = max(3, src.production * 2)  # keep 2 turns of production
    max_send = max(0, src.ships - reserve)
    
    return min(max_send, max(needed, 1))
```

**Key insight from orbit_lite**: The capture floor is the single most impactful calculation in the engine. The orbit_lite engine's `capture_floor` dynamically computes the required ships per target for each arrival turn k=1..H, inflating it by `beta * rho(k) * enemy_mass(target)` where enemy_mass is a distance-decayed sum of enemy garrisons. This is why orbit_lite never over-commits to attacks the enemy will reinforce — it simply marks those candidates as `clears_floor=False` and they don't get considered.

**Implementation recommendation**: Start with the simple version (works well enough to beat starter), then add ETA-dependent sizing and reinforcement-awareness for the full benefit.

#### Strategy 5: Grouped Multi-Source Attacks ─ Simultaneous Arrival

**Source**: ORACLE bot, comet_reaper attempt (DISCARD in isolation)

**Concept**: Against a strong enemy planet, single-source attacks may fail. Coordinate attacks from multiple planets to arrive on the SAME turn.

**The critical insight from the TIMELINE**: Staggered arrival (first fleet arrives, gets destroyed, second fleet arrives later) is NEGATIVE EV — the first fleet is wasted. Only simultaneous arrival (within ±1 turn) works.

**The reason it's hard**: Fleet speeds vary by ship count (log scale). Two fleets from different planets at different distances with different sizes will naturally arrive at different times. Calculating the exact split and timing is non-trivial.

**Practical implementation for a simpler Python bot**:
```python
# Sort all source-target combinations by arrival time
grouped_attacks = defaultdict(list)  # target_id -> [(arrival_turn, source, ships, angle)]
for mp in my_planets:
    for t in enemy_targets:
        result = intercept(mp, t, mp.ships)
        if result:
            arrival, angle, _ = result
            send = min(mp.ships - reserve, needed)
            grouped_attacks[t.id].append((arrival, mp, send, angle))

# Only fire if the SUM of ships arriving within the same ±1 turn window
# exceeds the target's defense (including production during flight)
for tgt_id, attacks in grouped_attacks.items():
    attacks.sort(key=lambda x: x[0])  # sort by arrival
    target = planet_by_id[tgt_id]
    needed = target.ships + 1 + target.production * attacks[0][0]
    
    # Find the first "wave" of arrivals within 1 turn of each other
    wave_arrival = attacks[0][0]
    wave_ships = 0
    for arrival, mp, send, angle in attacks:
        if arrival > wave_arrival + 1:
            break  # ships arrive too late, stop
        wave_ships += send
    
    if wave_ships >= needed:
        # Launch the wave
        for arrival, mp, send, angle in attacks:
            if arrival > wave_arrival + 1:
                break
            moves.append([mp.id, angle, int(send)])
```

**Warning from TIMELINE**: This was DISCARD'd for comet_reaper because the orbit_lite engine's single-source moves already capture 95% of profitable opportunities. But for a bot NOT using orbit_lite (i.e., a pure heuristic), multi-source coordination is a significant advantage.

---

### 4. Fleet Management & Energy Optimization

**Energy mechanics**: In Orbit Wars, there is no separate "energy" resource. Ships are the only resource. Each planet produces `production` ships per turn. Fleet launch costs are zero — you just spend the ships.

**Key resource management insights**:

1. **Production is king**. The player with more production wins. Production grows with planet count. Early expansion creates a compounding advantage. This is why the starter bot's 20-ship minimum is crippling — it delays expansion to orbiting planets, letting the opponent build a production lead.

2. **Minimum garrison reserve**. Always keep at least `max(3, production * 2)` ships on each planet. This ensures the planet can survive one turn of production and rebuild. **juandalfonso's formula**: `reserve = max(params["min_defense"], p.production * 2)`. The ORACLE bot uses `reserve = max(3, mp[6] * 2)` where `mp[6]` is production.

3. **Marginal ship value decreases with distance**. A ship on a frontline planet is worth more than a ship on a backline planet. This is the "regroup" concept in orbit_lite — the engine actively moves ships from safe backline planets to stressed frontline planets. Implement as: `if pressure[planet] - pressure[other] > delta: send surplus ships along the gradient`.

4. **Comet expiration**. Ships left on a comet planet when it expires are deleted. **Evacuate them 4 turns before expiry** to the nearest sun-clear friendly or neutral planet. The comet_reaper bot implements this as a post-processing step.

5. **The "safe drain" principle**. Don't drain a planet below its production capacity. orbit_lite's `safe_drain` computes: for each source, project the garrison trajectory forward H steps, and drain the maximum that still keeps positive garrison. In simpler terms: `max_send = max(0, ships - production * 2 - 1)`.

---

### 5. Concrete Game Theory Insights

#### Ship Count Breakpoints

| Ships | Fleet Speed | Notes |
|-------|-------------|-------|
| 1 | 1.00 | Slowest possible |
| 10 | 2.11 | Speed doubles at ~10 ships |
| 50 | 3.16 | |
| 100 | 3.85 | Typical mid-game fleet |
| 300 | 4.69 | |
| 1000 | 6.00 | Speed cap |

**Insight**: There's diminishing returns on fleet speed per ship. Going from 1→10 ships doubles speed (1→2.11), but 100→1000 only goes from 3.85→6.0. For long-distance attacks, better to send one 100-ship fleet than five 20-ship fleets (speed 3.85 vs 2.47).

#### Timing Advantages

1. **Early rush beats turtle** (turns 1-30). The player who captures 2-3 extra planets in the first 30 turns has ~2.5× production by turn 100. The starter bot only attacks static planets with 40+ ships — it barely expands at all. A rush bot that captures nearby orbiting neutrals in the first 10 turns wins the production war.

2. **Comet windows**. Comets spawn at turns 50, 150, 250, 350, 450. They're free planets with a short lifespan (typically 20-35 turns). The optimal comet strategy:
   - Capture a comet within 5 turns of spawn (when it has ~1-3 ships)
   - Use its production for 10-20 turns
   - Evacuate ships 4 turns before expiry
   - **DO NOT** invest in comets if an enemy planet is right next to it — they'll take it from you and use it against you

3. **FFA sandbagging**. If you're the leader in a 4-player game, the other 3 will attack you. The ORACLE bot detects this: `if my_ship_share > 0.35: go defensive, stop expanding`. This prevents being eliminated first. Prioritize attacking the runaway leader (ship_share > 0.36), not the weakest player.

4. **Endgame timing**. In the last 40 turns (of 500), parked ships earn no points. At turn 460+, convert ALL surplus ships into attacks. The optimal endgame is: every planet sends 95% of its ships at the nearest enemy or neutral planet. Even if you lose the fleet, those ships count toward your total while in transit.

5. **The "close ratio"**. juandalfonso found that when you have 4× more planets than a specific enemy, you can switch to all-out kill mode (min_defense=1, max_frac=0.95, all sources targeting same enemy). This finishes games in ~20 turns vs ~70 turns.

#### Combat Mechanics Deep Dive

The fleet arriving at a planet fights the garrison. The largest fleet wins (not proportional). This is key:

- If attacker has 100 ships and defender has 80: attacker wins, survives with 20 ships, defender is eliminated
- If attacker has 80 and defender has 80: attacker loses ALL ships, defender takes 80 damage (survives with 0 + production)
- If attacker has 80 and defender has 100: attacker loses all, defender survives with 20

**Never send exactly equal forces to a defender — you need > defender to win, and MORE than "defender + production * flight_turns" to account for growth.**

---

### 6. Existing Open-Source Bots

| Bot | GitHub | Approach | Performance |
|-----|--------|----------|-------------|
| **comet_reaper** | /tedtop/orbit-wars | orbit_lite engine clone + comet evac | ~1235 Elo (public #415) |
| **schmeekler** | /tedtop/orbit-wars | comet_reaper + static planet bonus | beats comet_reaper 72% 2P |
| **ORACLE** | /VampFay/ORACLE-Orbit-Wars | Multi-phase heuristic + beam search | 83.3% vs starter, 67.5% vs baseline |
| **PlanetPolicy** | /MarianodelRio/OrbitWars | Entity transformer + PPO (RL) | Trained on heuristic pool |
| **juandalfonso v11** | /juandalfonso/orbit-wars-bot | Phase-aware heuristic | 431 Kaggle score (vs 338 baseline) |
| **Nexus Wars starter** | (in kaggle-envs) | Static-only, 20-ship min, half-send | Basement tier |

**Notable finding from TIMELINE**: The top-1 bot (1793 Elo) used PPO over orbit_lite macro-parameters (aggression level, target priority, fleet-split ratio — a handful of floats playing over the engine's micro). No one beat the engine by replacing it. All competitors using raw-action PPO hit a 23% ceiling vs greedy.

---

### 7. Implementation Priority for a Python Agent

Given strict compute limits (~1s/turn, slow sandbox CPU), here's the recommended build order:

**Tier 1 (immediate, beats starter ≥80%)**:
1. Phase-aware state machine (expansion → consolidation → endgame)
2. Orbital intercept with 6-iteration prediction
3. Sun-crossing avoidance
4. `required_ships` calculation with ETA awareness
5. No duplicate targets per turn

**Tier 2 (competitive, +100-200 Elo)**:
6. Static planet scoring bonus (1.5×)
7. ETA-aware capture floor with reinforcement risk
8. Endgame suicide surge (last 40 turns)
9. Minimum defense reserve = `max(3, production * 2)`
10. Multi-source coordinated attacks with simultaneous arrival

**Tier 3 (advanced, +200+ Elo)**:
11. Fleet regroup (move backline ships to frontline)
12. Comet timing awareness (capture + evacuate)
13. FFA sandbagging (leader avoidance)
14. Opponent modeling (beam search, 3-ply MCTS, or Boltzmann)
15. Simple value function over game features

**Compute budget notes from TIMELINE**: A turn takes 6-7ms median with orbit_lite (PyTorch). Pure Python heuristics should be <1ms. The Kaggle sandbox gives ~1s with 5× slowdown for tournament mode. Any purely heuristic Python agent will have 100-200ms of compute budget per turn — more than enough for all Tier 1-2 strategies.
