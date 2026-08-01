# F1 — Competitive Orbit Wars / Planet Wars bot winners

## Key claims

- **Google AI Challenge 2010 "Planet Wars" winner = "Gauss" (Mikel Bel / melisgl).**
  Pure-Lisp entry. Core ideas: (a) net-ship **surplus** valuation per planet,
  (b) **futures** lookahead (simulate N turns then evaluate), (c) **alpha-beta**
  search over fleet-launch actions, (d) **safety-horizon** so the bot never
  "dies but doesn't know it yet." Source: melisgl/planet-wars `player.lisp`.
- **Simon Lucas / TeamTitans** — UK creator of Planet Wars; repeatedly top
  leaderboard in Planet Wars and the later Orbit Wars competitions. Approach:
  positional evaluation + shallow search; strong on the standard starter bots.
  Source: `simonlucas.github.io/planetwars-rts`.
- **Kaggle "Orbit Wars" 1st-place solution** — transformer policy over orbital
  bodies. ~200M params, **15B** self-play steps, pair-attention, int8 quantized,
  4× rotation TTA. Source: Kaggle Orbit Wars (DuckDuckGo result).
- **vkhydras `LAST_HEURISTIC` (#14)** — current leaderboard peak (lb1166 /
  lb1152). Pure-Python, ~190 hand-tuned constants, orbital prediction,
  reserve-walk forward sim, sun avoidance, multi-prong.
- **kvatsa5** hybrid — forward-sim 110-turn + 7 mission types + orbital
  mechanics + sun avoidance; strong 4P strategy.
- **Local orbit-wars planet-transformer (AGENTS.md project notes):** conv1d
  embedding (4 residual blocks 10→128, k=5, GELU, LayerNorm) → masked global
  avg pool → linear 128→256 → 7-layer ModernBERT encoder (hidden=256, 4 heads,
  QKV=768, MLP 256→768→384→256 GELU, Pre-LN, position_ids=0 RoPE-identity) →
  launch head (linear 256→1, sigmoid) + target-attention head (separate Q/K
  256→256, 4 heads, learnable head_weights, softmax over bodies). 68 arrays,
  **4.3M params**, **300B** self-play REINFORCE, int8 per-tensor symmetric
  (scale=max(|w|)/127), gzip(9)+base85 = 4.18 MB < 4.5 MB, **4× rotation TTA**,
  forward sim **T=20**. Opponent pool: random/starter/fortress/viper/chimera/
  chimera-np. Source: `bc_all_in_jax_model.py`, `quantize_orbitwars_weights.py`,
  AGENTS.md.
