# F2 — Orbital mechanics & hard constraints (Orbit Wars / Planet Wars)

## Key claims

- **Fleet angular speed = `angular_velocity` (a per-match constant).** Fleets move
  along circular orbits at this fixed angular rate; linear speed =
  `angular_velocity * radius_from_center`. Outer planets have larger radius →
  faster linear speed but need to cover more angular distance. Source:
  vkhydras #14 constants; `nexus_wars.py` engine.
- **Travel time ≈ `angular_distance / angular_velocity`** (mod 2π), clamped to
  shortest angular arc. fleets take `ceil(angular_distance/angular_velocity)`
  turns to reach the target angle. Source: vkhydras #14 prediction funcs;
  `finalize_chris.py` orbital prediction.
- **Sun avoidance is mandatory.** Bodies orbit a central sun (radius ≈1.0 in
  normalized coords). A fleet whose angular path passes through the sun
  (crosses r < sun_radius) is **destroyed**. vkhydras: `sun_dist` /
  `sun_radius` checks; finalize_chris: "Avoid launching through sun."
  Satirist: "never send a fleet through the sun." Source: vkhydras #14,
  finalize_chris.py HEURISTIC_CODE.
- **Comets removed.** Planet tuple = `[id, owner, x, y, radius, ships,
  production, energy, energyCap, energyRegen]` — no comet field. "Comets
  removed." Source: AGENTS.md.
- **Production** is a per-planet integer (ships generated per turn). Engine
  generates up to 40 planets (4-fold symmetry) — handle max_planets ≥ 48.
  Source: AGENTS.md; `nexus_wars.py`.
- **Fleet capacity:** up to 200 fleets per map — handle max_fleets ≥ 200.
  Source: AGENTS.md.
- **Energy overlay (Nexus Wars):** energy_cap=100, energy_regen=5,
  launch_energy_cost=20. **Skip launches from planets with energy < 20.**
  Source: AGENTS.md; finalize_chris.py `energy gate`.
- **All-in launch sends ALL ships** (no fractional head) — when committing,
  send the entire garrison reserve. Source: AGENTS.md.
