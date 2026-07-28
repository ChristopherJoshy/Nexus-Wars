# Personal Agent — Chris.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a self-contained Python bot (`chris.py`) using an adapted Orbit Wars 3-4M param transformer with PPO, trained on RTX 4050 in WSL, that plays Nexus Wars with energy awareness.

**Architecture:** Clone kaggle-orbit-wars repo into `test-bots/personal_agent/`. Port Nexus Wars engine to Rust (PyO3 module) for fast training. Adapt observation encoder for energy features + angle-based actions. Train with PPO self-play. Quantize weights and bake into single-file bot.

**Tech Stack:** Rust (PyO3 + numpy), Python 3.12, PyTorch, NVIDIA RTX 4050 6GB

## Global Constraints

- Everything in `test-bots/personal_agent/`
- Final deliverable: single `chris.py` file with base64-encoded weights
- Training: RTX 4050 6GB, max 4 hours
- Model: 3-4M parameters
- Must handle Nexus Wars energy system (energy, energyCap, energyRegen, launch cost 20)
- Must use angle-based actions `[source_id, angle_radians, ships]`
- 1v1 only
- Subprocess protocol: JSON stdin/stdout, 1s per-turn timeout

---

### Task 1: Adapt Observation Format for Nexus Wars

**Files:**
- Modify: `python/owl/agent/kaggle_observation.py`
- Modify: `python/owl/rl.py` (encoding functions)

**Interfaces:**
- Consumes: Nexus Wars engine observation dict with 10-element planet tuples, 8-element fleet tuples
- Produces: Tensor observation with energy features for model

- [ ] **Step 1: Update planet tuple parsing**

Nexus Wars planet: `[id, owner, x, y, radius, ships, production, energy, energyCap, energyRegen]` (10 elements)
Orbit Wars planet: `[id, owner, x, y, radius, ships, production]` (7 elements)

Update `python/owl/agent/kaggle_observation.py`:
- Add `energy`, `energyCap`, `energyRegen` fields to Planet tuple
- Update `PLANET_*_INDEX` constants
- Add these fields to `to_rl_observation()` output

- [ ] **Step 2: Update fleet tuple parsing**

Nexus Wars fleet: `[id, owner, x, y, angle, from_planet_id, ships, launchedStep]` (8 elements)
Orbit Wars fleet: `[id, owner, x, y, angle, from_planet_id, ships]` (7 elements)

Update `python/owl/agent/kaggle_observation.py`:
- Add `launchedStep` to Fleet tuple
- Add to `to_rl_observation()` output

- [ ] **Step 3: Add energy observation channels to rl.py**

In `python/owl/rl.py`:
- Create `NEXUS_PLANET_CHANNELS` constant (replaces `PLANET_CHANNELS` from Rust)
- Add 3 extra channels for energy, energyCap, energyRegen
- Update the Python `encode_python_observation()` to include energy features
- Remove comet channels
- Remove 3p/4p player slots (keep OUTER_PLAYER_SLOTS=2 for 1v1)

### Task 2: Create Rust Nexus Wars Engine

**Files:**
- Create: `src/nexus_wars/mod.rs`
- Create: `src/nexus_wars/state.rs`
- Create: `src/nexus_wars/env.rs`
- Create: `src/nexus_wars/geom.rs`
- Create: `src/nexus_wars/map_gen.rs`
- Modify: `src/lib.rs` (add nexus_wars module + PyO3 bindings)
- Create: `src/nexus_vec_env.rs` (vectorized env wrapper)

**Interfaces:**
- Consumes: Python engine logic from `nexus_wars.py`
- Produces: `NexusWarsEnv` — reset(), step(), obs_shapes(), encode_observation()

- [ ] **Step 1: Create state.rs** — Planet, Fleet, LaunchAction, GameConfig, GameState structs with energy fields

```rust
// state.rs — Core data structures for Nexus Wars

pub const BOARD_SIZE: f64 = 100.0;
pub const CENTER: f64 = 50.0;
pub const SUN_RADIUS: f64 = 10.0;
pub const ROTATION_RADIUS_LIMIT: f64 = 50.0;
pub const PLANET_CLEARANCE: f64 = 7.0;
pub const MIN_PLANET_GROUPS: i32 = 5;
pub const MAX_PLANET_GROUPS: i32 = 10;
pub const MIN_STATIC_GROUPS: usize = 3;
pub const ENERGY_CAP: i32 = 100;
pub const ENERGY_REGEN: i32 = 5;
pub const LAUNCH_ENERGY_COST: i32 = 20;

#[derive(Clone, Copy, Debug)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

#[derive(Clone, Debug)]
pub struct Planet {
    pub id: u32,
    pub owner: i32,        // -1 = neutral
    pub x: f64,
    pub y: f64,
    pub radius: f64,
    pub ships: i32,
    pub production: i32,
    pub energy: i32,
    pub energy_cap: i32,
    pub energy_regen: i32,
}

#[derive(Clone, Debug)]
pub struct Fleet {
    pub id: u32,
    pub owner: i32,
    pub x: f64,
    pub y: f64,
    pub angle: f64,
    pub from_planet_id: u32,
    pub ships: i32,
    pub launched_step: i32,
}

pub struct LaunchAction {
    pub from_planet_id: u32,
    pub angle: f64,
    pub ships: i32,
}

pub struct GameConfig {
    pub episode_steps: i32,
    pub ship_speed: f64,
    pub energy_cap: i32,
    pub energy_regen: i32,
    pub launch_energy_cost: i32,
}

pub struct GameState {
    pub step: i32,
    pub angular_velocity: f64,
    pub planets: Vec<Planet>,
    pub initial_planets: Vec<Planet>,
    pub fleets: Vec<Fleet>,
    pub next_fleet_id: u32,
    pub config: GameConfig,
}
```

- [ ] **Step 2: Create geom.rs** — Distance, swept-pair collision, point-to-segment distance (port from Python)

```rust
// geom.rs — Geometry utilities ported from nexus_wars.py

pub fn distance(p1: &Point, p2: &Point) -> f64 {
    ((p1.x - p2.x).powi(2) + (p1.y - p2.y).powi(2)).sqrt()
}

pub fn point_to_segment_distance(p: &Point, v: &Point, w: &Point) -> f64 {
    let l2 = (v.x - w.x).powi(2) + (v.y - w.y).powi(2);
    if l2 == 0.0 { return distance(p, v); }
    let t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y) / l2).clamp(0.0, 1.0);
    let projection = Point::new(v.x + t * (w.x - v.x), v.y + t * (w.y - v.y));
    distance(p, &projection)
}

pub fn swept_pair_hit(a: &Point, b: &Point, p0: &Point, p1: &Point, r: f64) -> bool {
    let d0x = a.x - p0.x;
    let d0y = a.y - p0.y;
    let dvx = (b.x - a.x) - (p1.x - p0.x);
    let dvy = (b.y - a.y) - (p1.y - p0.y);
    let a_coeff = dvx * dvx + dvy * dvy;
    let b_coeff = 2.0 * (d0x * dvx + d0y * dvy);
    let c = d0x * d0x + d0y * d0y - r * r;
    if a_coeff < 1e-12 { return c <= 0.0; }
    let disc = b_coeff * b_coeff - 4.0 * a_coeff * c;
    if disc < 0.0 { return false; }
    let sqrt_disc = disc.sqrt();
    let t1 = (-b_coeff - sqrt_disc) / (2.0 * a_coeff);
    let t2 = (-b_coeff + sqrt_disc) / (2.0 * a_coeff);
    t2 >= 0.0 && t1 <= 1.0
}

pub fn fleet_speed(ships: i32, max_speed: f64) -> f64 {
    if ships <= 0 { return 0.0; }
    let s = ships as f64;
    let ratio = (s.ln() / 1000_f64.ln()).powf(1.5);
    1.0 + (max_speed - 1.0) * ratio
}
```

- [ ] **Step 3: Create map_gen.rs** — Port `generate_planets()` from Python

Port the 4-fold symmetric planet generation. Key points:
- Generate planet groups with 4-fold symmetry
- Static planets (outside rotation band) and rotating planets
- Assign home planets to players (player 0 gets first group, player 1 gets fourth group)
- All planets start with full energy (energy = energy_cap)

- [ ] **Step 4: Create env.rs** — Port `interpreter()` from Python

The core game step:
1. Process actions: validate energy >= launchEnergyCost, deduct energy, create fleets
2. Production + energy regen for owned planets
3. Compute planet end-of-tick positions (rotation)
4. Move fleets (speed formula + swept-pair collision)
5. Apply planet movement
6. Combat resolution (multi-attacker SUM)
7. Check termination

```rust
pub fn reset(config: GameConfig, rng_seed: u64) -> GameState { ... }
pub fn step(state: &mut GameState, actions: &[Vec<LaunchAction>]) -> StepResult { ... }
```

- [ ] **Step 5: Create vec_env.rs** — Vectorized environment wrapper

```rust
pub struct NexusVecEnv {
    envs: Vec<GameState>,
    config: GameConfig,
    n_envs: usize,
}
impl NexusVecEnv {
    pub fn new(n_envs: usize, config: GameConfig) -> Self { ... }
    pub fn reset(&mut self) -> Vec<EncodedObs> { ... }
    pub fn step(&mut self, actions: &[Vec<Vec<LaunchAction>>]) -> StepResultBatch { ... }
}
```

- [ ] **Step 6: Add PyO3 bindings in lib.rs**

Expose NexusVecEnv via PyO3:
```rust
#[pyclass]
struct PyNexusVecEnv { ... }

#[pymethods]
impl PyNexusVecEnv {
    #[new]
    fn new(n_envs: usize, config: HashMap<String, f64>) -> Self { ... }
    fn reset(&mut self, py: Python) -> PyObject { ... }
    fn step(&mut self, py: Python, actions: PyObject) -> PyObject { ... }
}
```

### Task 3: Create Model Config (3-4M params)

**Files:**
- Create: `configs/nexus_4m.yaml`

- [ ] **Step 1: Write config yaml**

```yaml
env:
  obs_spec: nexus_entity_based
  action_spec: pure
  n_envs: 256
  two_player_weight: 1.0
  reward_mode: win_only

model:
  model_arch: stateless_transformer_v1
  embed_dim: 256
  depth: 6
  n_heads: 8
  mlp_ratio: 4.0
  n_scratch_tokens: 4
  activation: gelu
  critic_mode: softmax
  value_mode: win_loss
  player_count_adapters_enabled: false
  actor:
    action_spec: pure
    n_angle_mixtures: 8
    n_fleet_size_mixtures: 4
    min_fleet_size: 3

optimizer:
  lr: 3e-4
  betas: [0.9, 0.999]
  weight_decay: 0.0

rl:
  horizon: 64
  ppo_epochs: 1
  segments_per_minibatch: 1
  gamma: 1.0
  gae_lambda: 0.95
  clip_coef: 0.2
  vf_coef: 0.5
  ent_coef: 0.01
  max_grad_norm: 0.5

runtime:
  n_runtime_gpus: 1
```

### Task 4: Create Training Entrypoint

**Files:**
- Create: `scripts/train_nexus.py`
- Create: `python/owl/nexus_rl.py` (Nexus Wars specific env wrapper)

- [ ] **Step 1: Create nexus_rl.py** — Python wrapper for the Rust NexusVecEnv

```python
class NexusVectorizedEnv:
    """Python wrapper around Rust NexusVecEnv, matching VectorizedEnv interface."""
    
    def __init__(self, n_envs, obs_spec, action_spec, ...):
        self._env = PyNexusVecEnv(n_envs, config)
    
    def reset(self) -> ObsBatch:
        ...
    
    def step(self, actions: ActionBundle) -> tuple[ObsBatch, Tensor, Tensor, list]:
        ...
```

- [ ] **Step 2: Create train_nexus.py** — Training entrypoint

```python
# Based on run_ppo.py but simplified for Nexus Wars
# 1. Load config
# 2. Create env
# 3. Create model
# 4. Create optimizer
# 5. Run PPO training loop
```

### Task 5: Create Bake Script

**Files:**
- Create: `scripts/bake.py`

- [ ] **Step 1: Write bake.py**

```python
# Takes a trained checkpoint and produces chris.py
# 1. Load checkpoint weights
# 2. Apply int8 quantization
# 3. Base64 encode the bytes
# 4. Generate chris.py with:
#    - Base64 weight blob
#    - Model architecture code (compact ~200 lines)
#    - decode_weights() function
#    - inference loop (stdin/stdout JSON)
```

### Task 6: Final Deliverable — chris.py

**Files:**
- Create: `test-bots/personal_agent/chris.py` (generated by bake.py)

- [ ] **Step 1: Architecture file** — Compact model definition (~200 lines)
- [ ] **Step 2: Weight blob** — Base64-encoded int8 quantized weights
- [ ] **Step 3: Inference loop** — Read JSON from stdin, run model, write JSON to stdout
- [ ] **Step 4: Test against engine** — Run `python run_match.py --agents random chris --out replay.json`
