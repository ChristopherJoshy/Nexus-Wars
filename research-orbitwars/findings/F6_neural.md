# F6 — Neural / learned architecture & training details

## Key claims

- **Orbit-wars planet-transformer (`bc_all_in_jax_model.py`):**
  conv1d embedding (4 residual blocks: 10→128 channels, kernel=5, GELU,
  LayerNorm; masked global avg pool; linear 128→256) → 7-layer ModernBERT
  encoder (hidden=256, 4 heads, QKV=768, MLP 256→768→384→256 with GELU gate,
  Pre-LN, position_ids=0 RoPE-identity) → launch head (linear 256→1, sigmoid)
  + target-attention head (separate Q/K 256→256, 4 heads, learnable
  head_weights, softmax over bodies). 68 weight arrays, **4.3M params**.
  Source: bc_all_in_jax_model.py.
- **Observation encoder (AGENTS.md):** 10 features × 20 timesteps × n_bodies:
  `step, production, radial(from center 50,50), angle, my_ships,
  neutral_ships, enemy_ships, ships_for_capture`. 10 input channels →
  matches conv1d `in_channels=10`. Source: AGENTS.md.
- **Int8 quantization (quantize_orbitwars_weights.py):** per-tensor symmetric
  int8, scale = max(|w|)/127. Dropped `tok_embeddings.weight` (unused).
  gzip(level 9) + base64 → 4.18 MB < 4.5 MB limit. Source:
  quantize_orbitwars_weights.py.
- **4× rotation TTA:** batch 4 angle-rotated views (angle += k·π/2, k=0..3),
  single forward pass, average launch_logits + target_logits. Source:
  AGENTS.md.
- **Training:** REINFORCE (policy gradient), **300B** self-play steps vs
  opponent pool (random, starter, fortress, viper, chimera, chimera-np).
  Kaggle 1st-place reports 15B self-play on a ~200M-param transformer.
  Source: AGENTS.md; train_chris.py.
- **Validation:** opponent = built-in "random"; success = survive ≥1 turn +
  valid JSON actions. Source: AGENTS.md (Validation).
- **Runtime limits for submission:** 1 s/turn, 512 MB RAM, 500 max steps,
  no torch/tf (exceeds 512MB), pure Python + numpy only. Source: AGENTS.md.
