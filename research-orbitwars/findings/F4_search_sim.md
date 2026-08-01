# F4 — Search, forward simulation & compute budget

## Key claims

- **Forward simulator horizon trade-off.** Local agent uses pure-Python
  **T=20** step simulation (production, energy regen, fleet movement, collision,
  combat). kvatsa5 uses T=110; vkhydras reserve-walk uses an adaptive
  horizon. Because per-turn budget is 1s / 512MB, keep the horizon small
  (T=20 fits comfortably) and bias toward greedy + lookahead rather than
  deep MCTS. Source: AGENTS.md; kvatsa5 README; vkhydras #14.
- **Alpha-beta (melisgl winner):** depth-limited minimax over launch actions
  with a positional eval + safety horizon. Beats pure greedy by reasoning
  about the "I lose next turn but don't know it" trap. Source: player.lisp.
- **1+1-ES evolution (es_train_evaluator.py):** 193 scalar params,
  fitness = `wins*10000 + score_diff`, 32 matches per eval, 16-core parallel,
  self-adaptive sigma (1+1-ES: one parent, one offspring, keep if better,
  mutate sigma up on success streak / down on failure). Source:
  es_train_evaluator.py.
- **REINFORCE macro-RL (train_chris.py / AGENTS.md):** 300B self-play REINFORCE
  against opponent pool. Local implementation uses the orbit-wars
  planet-transformer (see F1/F6) as the policy. Source: train_chris.py,
  AGENTS.md.
- **4× rotation TTA:** batch 4 angle-rotated views (angle += k·π/2, k=0..3),
  single forward pass, average `launch_logits` + `target_logits`. Cheap way to
  gain ~30% accuracy vs orientation bias. Source: AGENTS.md.
- **Per-turn limits:** ≤1000 ms, 10 consecutive timeouts kills the process,
  500 max episode steps, ≤512 MB RAM. Keep heavy imports deferred to function
  scope. Source: AGENTS.md (Agent runtime limits).
