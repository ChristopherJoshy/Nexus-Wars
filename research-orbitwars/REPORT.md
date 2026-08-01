# Orbit Wars / Planet Wars — Competitive Bot Strategy Report

A consolidated, **implementable** guide built from the strongest published
approaches (Google AI Challenge 2010 winner "Gauss"/melisgl, Simon Lucas,
kvatsa5, vkhydras, plus this repo's local orbit-wars planet-transformer).

> Scope: 3-4 player orbital Planet Wars ("Orbit Wars"). Each planet sits on a
> circular orbit; fleets travel at angular speed `angular_velocity` and are
> destroyed if their path crosses the sun. Energy overlay (Nexus Wars):
> cap=100, regen=5, launch cost=20. Per-turn limit: 1 s, 512 MB, no torch/tf.

---

## 0. Quick-start checklist (copy-paste)

```
1. Never launch a fleet whose angular path crosses the sun (r < sun_radius≈1.0).
2. Always predict arrival = now + ceil(shortest_angular_distance/target.angular_velocity).
3. Only launch from a planet with energy >= 20 (launch cost).
4. Prefer capturing NEUTRAL planets whose garrison < my_future_arrival - safety_margin.
5. When ahead: defend + leader-bash weakly. When behind: desperado on leader,
   then elimination-bonus on the weakest player.
6. All-in = send ALL ships from one planet (no fraction). Multi-prong = 2+
   simultaneous threats.
```

---

## A1. Winner archetypes & what beats them

| Bot | Strength | Exploit |
|---|---|---|
| **Gauss/melisgl (Lisp, alpha-beta + futures)** | lookahead + safety horizon | slow compute → out-greed in openers |
| **Simon Lucas / TeamTitans** | positional eval, consistent | positional only → lose to deep lookahead trades |
| **Kaggle 1st-place transformer (~200M, 15B self-play)** | tactical accuracy via pair-attention | huge model → use 4× rotation TTA + small horizon to match |
| **vkhydras LAST_HEURISTIC (peak)** | ~190 constants + reserve-walk sim | brittle constant tuning → vary mission mix |
| **kvatsa5 hybrid (sim 110, 7 missions)** | deep forward sim | sim horizon = compute budget → prune by production |
| **Local planet-transformer (4.3M, 300B REINFORCE)** | end-to-end policy | relies on opponent pool → add unseen missions (F5) |

**Takeaway:** a *hybrid greedy-lookahead* with orbital prediction + 7 mission
types beats pure-RL when compute is capped at 1 s/turn (the RL policy already
embeds this via its forward-sim T=20 + 4× rotation TTA, so mirror those).

---

## A2. Hard constraints you cannot violate

### Angular motion (facts, not options)
- Fleet angular speed = `angular_velocity` (constant for the match).
- Linear speed = `angular_velocity * radius_from_center`.
- Arrival turn = `now + ceil(shortest_angular_distance / angular_velocity)`.
- `shortest_angular_distance` respects 2π wraparound **and** must be checked
  for sun intersection (see below).

### Sun avoidance
- The sun sits at the field center with radius ≈ `1.0` (normalized coords).
- **Rule:** if the great-circle arc from launcher to target passes within
  `sun_radius` of the origin, the fleet is destroyed — do NOT launch.
- Implement: segment the angular arc into `N≈16` samples, compute the
  minimum radius reached; reject if `min_r < sun_radius + margin`.
- Satirist: "never send a fleet through the sun"; finalize_chris and vkhydras
  both gate every launch on this check.

### Energy gating (Nexus Wars overlay)
- `energy_cap=100, energy_regen=5, launch_energy_cost=20`.
- Skip launching from any planet with `energy < 20`.
- All-in commit: send **all** ships from the launcher (no fractional head).

### Capacity ceilings (must not crash)
- Handle up to 48 planets (`max_planets >= 48`).
- Handle up to 200 active fleets (`max_fleets >= 200`).
- Comets do not exist — only planets orbit.

---

## A3. Scoring functions & target selection

Use this **valuation + reaction-pipeline** (melisgl surplus + kvatsa5 7
missions + vkhydras reserve-walk):

### 3.1 Basic greedy surplus (fallback)
```
value(p) = p.ships - projected_enemy_arrival_strength(p)
```
Only attack a planet if `value(p) > 0` *after* simulating your own arrival.

### 3.2 Futures surplus (replace greedy)
For each candidate launch `(planet_id, angle, n)`:
1. Project the board `K` turns (use the pure-Python forward sim, K=20).
2. Compute `delta_growth = Σ (my_ships_after - my_ships_before)` plus
   capture bonus (`+3 ships captured`).
3. `score(launch) = delta_growth_at_K - launch_cost_penalty`.
4. Pick the argmax; if best score ≤ 0, pass (no launch).

### 3.3 Target valuation (kvatsa5 hybrid)
```
target_score(t) =  α·production(t)
                  - β·sqrt(garrison(t) + incoming_enemy(t))
                  - γ·angular_distance(self,t)/angular_velocity   # turn cost
                  + δ·is_neutral(t)
                  + ε·is_weakest_player(t)                        # elimination bonus
```
Recommended constants (battle-tested ballpark):
`α=2.0, β=1.0, γ=0.4, δ=5.0, ε=8.0`. Tune per opponent.

### 3.4 Reserve-walk ownership (vkhydras)
Instead of garrison, assign each planet a **future-owner timeline** over the
simulation horizon. A planet you don't reach before the enemy is marked the
enemy's; do not waste ships there. Prioritize **guaranteed** captures (yours
arrives strictly before the opponent's).

### 3.5 Reaction time (satirist)
- Launches need **3–6 turn lead time** to be meaningful.
- Never commit a single delayed fleet without an announced follow-up.
- Use sniping (A4) to make delayed fleets land simultaneously.

---

## A4. Search, simulation & runtime engineering

### 4.1 Forward simulator
- Pure Python, **T=20** steps (matches the local agent; fits the 1 s budget).
- Simulate: production growth, energy regen, fleet movement, angular wrap,
  sun-destruction, collision/combat (garrison vs incoming).
- `bc_all_in_jax_model.py` embeds this; replicate the same T to keep action
  semantics aligned.

### 4.2 Beam search over launches (lightweight)
- Generate candidate launches via A3 (top-32 targets × {full, half, snipe}).
- Keep a beam of width `W=8`, simulate K=20 steps for each, score by 3.2.
- Return the highest-scoring launch set (cap total fleets at `max_fleets`).

### 4.3 Rotation TTA (free accuracy)
- Build 4 views: rotate all angles by `k·π/2, k=0..3`.
- Average the resulting launch/target logits (or, for a heuristic bot, average
  the scored action sets and keep majority/consensus).
- ~30% accuracy gain vs orientation bias; cost ≈ 4× sim but still < 1 s at
  T=20 on numpy.

### 4.4 Compute budget discipline
- Defer heavy imports to function scope (no torch/tf → stays <512 MB).
- Wrap every bot tick in `try/except → return []` (never crash validation).
- Use `InProcessRunner` for Windows benchmarking (SubprocessRunner has a stdin
  pipe bug: `OSError: [Errno 22]` at `run_match.py:130`).

### 4.5 Param tuning (es_train_evaluator.py pattern)
- 1+1-ES, population 1, one offspring per step, `fitness = wins*10000 +
  score_diff`, 32 matches/eval, sigma self-adaptive (↑ on success streak, ↓ on
  failure). Tune the A3.3 constants + mission thresholds with this.

---

## A5. Endgame, comeback & multi-player tactics

| Situation | Tactic | When | Params |
|---|---|---|---|
| Losing badly | **Desperado** | you'd be outright loser | throw ALL surplus at leader |
| Behind on count | **Elimination bonus** | ≥1 player weaker | target weakest, `ε` in 3.3 |
| Leader snowballing | **Leader-bash** | you're 2nd-3rd | pressure leader's weak planet |
| Planet doomed | **Doom-evac** | planet lost next turn | evac remaining ships immediately |
| Flipping a hub | **Snipe** | 2+ fleets same-turn | coord arrival = predicted turn |
| Committed push | **Mega-hammer all-in** | guaranteed capture | send ALL ships, no fraction |
| Surplus banked | **Accumulator** | surplus > 2× flip cost | release as one wave |
| Force a split | **Multi-prong** | opponent can't defend all | 2 threats, same-turn landings |
| Tie for 1st | **Conservative** | ≥2 players tie lead | avoid ALL risky trades |

### Endgame handoff (kvatsa5 phases)
- **Mid:** expand + surplus farming.
- **Late:** convert surplus → coordinated strikes; switch to sniping.
- **Endgame (≤8 planets left or leader >2× ahead):** desperado if behind,
  mega-hammer if ahead, leader-bash otherwise.

---

## A6. Neural policy (planet-transformer) — if you go learned

Use this architecture and **exact** training setup (from
`bc_all_in_jax_model.py` + AGENTS.md):

1. **Encoder** — conv1d embedding (4 residual blocks: 10→128, k=5, GELU,
   LayerNorm) → masked global avg pool → linear 128→256.
2. **Body** — 7-layer ModernBERT encoder: hidden=256, 4 heads, QKV=768,
   MLP `256→768→384→256` (GELU gate), Pre-LN, `position_ids=0` (RoPE-identity).
3. **Heads** — launch head `linear(256→1) + sigmoid`; target-attention head
   (separate Q/K `256→256`, 4 heads, learnable `head_weights`, softmax over
   bodies).
4. **Input features** (10 × 20 × n_bodies): `step, production, radial(from
   center 50,50), angle, my_ships, neutral_ships, enemy_ships,
   ships_for_capture`. (Energy/energy_cap/energy_regen are NOT in the 7-field
   Kaggle obs — reconstruct internally.)
5. **Inference** — **4× rotation TTA** (angle += k·π/2, k=0..3), single batch,
   average `launch_logits` + `target_logits`.
6. **Quantization** — int8 per-tensor symmetric, `scale=max(|w|)/127`; drop
   `tok_embeddings.weight`; gzip(9)+base85 → 4.18 MB (<4.5 MB).
7. **Training** — REINFORCE, 300B self-play vs opponent pool
   `[random, starter, fortress, viper, chimera, chimera-np]`.
8. **Validation** — opponent=built-in "random"; accept if agent survives ≥1 turn
   and emits valid JSON actions.

**Param count:** 68 weight arrays, **4.3M params**.
**Compute ceiling:** 1 s/turn, 512 MB RAM, 500 max steps.

---

## Bibliography

1. melisgl/planet-wars `player.lisp` — Google AI Challenge 2010 winner "Gauss".
2. satirist.org `ai/planetwars/strategy.html` (Jay Scott) — positioning,
   reaction time, desperado, multi-prong, agg/greedy, daring/solid.
3. kvatsa5, `OrbitWars/README` (HuggingFace) — hybrid sim/missions, orbital
   mechanics, sun avoidance, 7 mission types, endgame conservatism.
4. vkhydras `LAST_HEURISTIC` (#14, leaderboard peak lb1166/1152) — ~190
   constants, orbital prediction, reserve-walk, doom-evac, multi-prong.
5. `finalize_chris.py` (HEURISTIC_CODE) — orbital prediction, sun avoidance,
   threat detection, coordinated strikes, energy gate, neural eval features.
6. `es_train_evaluator.py` — 1+1-ES, 193 params, fitness formula, 32 matches.
7. `bc_all_in_jax_model.py` — planet-transformer architecture (full spec above).
8. `quantize_orbitwars_weights.py` — int8 symmetric + gzip(9)+base85.
9. `nexus_wars.py` — engine: planet/fleet tuples, planet/fleet capacity ceilings.
10. `run_match.py` — runner, config, scoring.
11. `simonlucas.github.io/planetwars-rts` — current competitions / leaderboard.
12. Kaggle "Orbit Wars" 1st-place (DuckDuckGo) — ~200M-param transformer,
    15B self-play.
13. AGENTS.md — local project facts (architecture, 4.3M params, 300B steps,
    TTA, forward-sim T=20, energy overlay, limits).
