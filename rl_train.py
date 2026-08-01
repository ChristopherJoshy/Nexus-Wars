"""
Hybrid RL training for chris.py.

Macro-action policy over 3 modes:
  0 = hold / defence only
  1 = expand-biased
  2 = attack-biased

Fast CPU-only training with simple policy gradient.
"""

from __future__ import annotations

import math, os, random, sys, time
from typing import Any, Dict, List, Tuple

import numpy as np

sys.path.insert(0, 'services/worker/engine/nexus_wars')
sys.path.insert(0, 'test-bots/personal_agent')

import chris as chris_mod
from run_match import make_runner, run_match

# ── Config ─────────────────────────────────────────────────────────────────────
TOTAL_STEPS = 80_000
ROLLOUT_LEN = 32
UPDATES = TOTAL_STEPS // ROLLOUT_LEN
LR = 1e-3
GAMMA = 0.99
ENT_COEF = 0.01
OBS_DIM = 32
HIDDEN = 128
NLAYERS = 2
MODEL_PATH = 'test-bots/personal_agent/chris_rl_policy.npz'

ACT_HOLD = 0
ACT_EXPAND = 1
ACT_ATTACK = 2


def encode_obs(obs: dict, me: int) -> np.ndarray:
    planets = obs.get("planets", [])
    fleets = obs.get("fleets", [])
    step = float(obs.get("step", 0)) / 500.0
    my = [p for p in planets if p[1] == me]
    enemy = [p for p in planets if p[1] != me and p[1] != -1]
    neutrals = [p for p in planets if p[1] == -1]
    feats = [
        step,
        float(obs.get("angular_velocity", 0.035)),
        float(len(my)), float(len(enemy)), float(len(neutrals)),
        float(sum(p[5] for p in my)) / 200.0,
        float(sum(p[5] for p in enemy)) / 200.0,
        float(sum(p[6] for p in my)) / 60.0,
        float(sum(p[6] for p in enemy)) / 60.0,
        float(len(fleets)),
        float(sum(1 for f in fleets if f[1] == me)),
        float(sum(1 for f in fleets if f[1] != me)),
    ]
    while len(feats) < OBS_DIM:
        feats.append(0.0)
    return np.array(feats[:OBS_DIM], dtype=np.float32)


class MLP:
    def __init__(self):
        self.params: Dict[str, np.ndarray] = {}
        d, h = OBS_DIM, HIDDEN
        self.params['W1'] = (np.random.randn(d, h) * np.sqrt(2.0 / d)).astype(np.float32)
        self.params['b1'] = np.zeros(h, dtype=np.float32)
        for i in range(2, NLAYERS + 1):
            self.params[f'W{i}'] = (np.random.randn(h, h) * np.sqrt(2.0 / h)).astype(np.float32)
            self.params[f'b{i}'] = np.zeros(h, dtype=np.float32)
        self.params['Wp'] = (np.random.randn(h, 3) * np.sqrt(2.0 / h)).astype(np.float32)
        self.params['bp'] = np.zeros(3, dtype=np.float32)

    def forward(self, x: np.ndarray) -> np.ndarray:
        z = np.maximum(0.0, x @ self.params['W1'] + self.params['b1'])
        for i in range(2, NLAYERS + 1):
            z = np.maximum(0.0, z @ self.params[f'W{i}'] + self.params[f'b{i}'])
        return z @ self.params['Wp'] + self.params['bp']

    def flat(self) -> np.ndarray:
        return np.concatenate([v.ravel() for v in self.params.values()])

    def set_flat(self, flat: np.ndarray):
        offset = 0
        for k in self.params:
            size = self.params[k].size
            self.params[k] = np.asarray(flat[offset:offset + size]).reshape(self.params[k].shape).astype(np.float32)
            offset += size

    def save(self, path: str):
        np.savez(path, flat=self.flat(), obs_dim=np.array([OBS_DIM]), hidden=np.array([HIDDEN]), nlayers=np.array([NLAYERS]))

    def load(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        data = np.load(path)
        if 'flat' not in data:
            return False
        self.set_flat(data['flat'])
        return True


def apply_macro(obs: dict, action: int) -> List[List]:
    try:
        base = chris_mod.agent_fn(obs)
    except Exception:
        base = []
    if action == ACT_HOLD:
        return []
    if action == ACT_ATTACK:
        enemy_ids = {p[0] for p in obs.get("planets", []) if p[1] != -1 and p[1] != obs.get("player", 0)}
        preferred = []
        for a in base:
            target_id = None
            planets = obs.get("planets", [])
            if planets and len(a) >= 2:
                sx = next((p[2] for p in planets if p[0] == a[0]), None)
                sy = next((p[3] for p in planets if p[0] == a[0]), None)
                if sx is not None and sy is not None:
                    angle = float(a[1])
                    tx = sx + math.cos(angle) * 1e9
                    ty = sy + math.sin(angle) * 1e9
                    best_id, best_d = None, 1e18
                    for p in planets:
                        if p[0] == a[0]:
                            continue
                        d = math.hypot(p[2] - tx, p[3] - ty)
                        if d < best_d:
                            best_d = d
                            best_id = p[0]
                    target_id = best_id
            if target_id in enemy_ids:
                preferred.append(a)
        return preferred or base
    return base


def make_agent(policy: MLP, player: int):
    def agent(obs: dict) -> List[List]:
        try:
            x = encode_obs(obs, player)
            logits = policy.forward(x)
            logits = np.asarray(logits).reshape(-1)
            logits = logits - np.max(logits)
            probs = np.exp(logits)
            probs = probs / (np.sum(probs) + 1e-8)
            action = int(np.random.choice(len(probs), p=probs))
            return apply_macro(obs, action)
        except Exception:
            try:
                return chris_mod.agent_fn(obs)
            except Exception:
                return []
    return agent


def collect_rollout(policy: MLP, seed: int, length: int) -> Dict[str, Any]:
    random.seed(seed)
    np.random.seed(seed)
    obs_buf: List[np.ndarray] = []
    act_buf: List[int] = []
    logp_buf: List[float] = []
    rew_buf: List[float] = []

    runners = [make_runner(make_agent(policy, 0)), make_runner(make_agent(policy, 1))]
    replay = run_match(runners, seed=seed)
    winner = replay.get("info", {}).get("winner", -1)
    steps = replay.get("steps", [])

    for idx, step_data in enumerate(steps[:length]):
        obs0 = step_data.get("observation", {})
        for player, obs in enumerate((obs0, dict(obs0, player=1))):
            x = encode_obs(obs, player)
            logits = policy.forward(x)
            logits = np.asarray(logits).reshape(-1)
            logits = logits - np.max(logits)
            probs = np.exp(logits)
            probs = probs / (np.sum(probs) + 1e-8)
            action = int(np.random.choice(len(probs), p=probs))
            logp = float(np.log(probs[action] + 1e-8))

            reward = -0.005
            my_ships = sum(p[5] for p in obs.get("planets", []) if p[1] == player)
            en_ships = sum(p[5] for p in obs.get("planets", []) if p[1] != player and p[1] != -1)
            reward += (my_ships - en_ships) * 0.0005

            obs_buf.append(x)
            act_buf.append(action)
            logp_buf.append(logp)
            rew_buf.append(reward)

    for i in range(len(act_buf)):
        player = i % 2
        if winner == player:
            rew_buf[i] += 1.0
        elif winner != -1:
            rew_buf[i] -= 1.0

    returns = np.zeros(len(rew_buf), dtype=np.float32)
    R = 0.0
    for t in reversed(range(len(rew_buf))):
        R = rew_buf[t] + GAMMA * R
        returns[t] = R
    advantages = returns - returns.mean()
    advantages = advantages / (advantages.std() + 1e-8)

    return {
        'obs': np.stack(obs_buf),
        'actions': np.array(act_buf, dtype=np.int64),
        'old_logp': np.array(logp_buf, dtype=np.float32),
        'advantages': advantages,
        'returns': returns,
        'winner': winner,
    }


def loss_and_grad(policy: MLP, batch: Dict[str, Any]) -> Tuple[float, np.ndarray]:
    obs = batch['obs']
    actions = batch['actions']
    old_logp = batch['old_logp']
    advantages = batch['advantages']

    logits = policy.forward(obs)
    logits = np.asarray(logits)
    logits = logits - np.max(logits, axis=1, keepdims=True)
    exp_logits = np.exp(logits)
    probs = exp_logits / (np.sum(exp_logits, axis=1, keepdims=True) + 1e-8)
    log_probs = np.log(probs + 1e-8)
    new_logp = log_probs[np.arange(len(actions)), actions]

    ratio = np.exp(new_logp - old_logp)
    clipped = np.clip(ratio, 1.0 - 0.2, 1.0 + 0.2)
    policy_loss = -np.minimum(ratio * advantages, clipped * advantages).mean()
    entropy = -np.sum(probs * np.log(probs + 1e-8), axis=1).mean()
    loss = float(policy_loss - ENT_COEF * entropy)

    base_flat = policy.flat()
    grad = np.zeros_like(base_flat)
    eps = 1e-3
    idx = np.random.choice(base_flat.size, size=min(base_flat.size, 256), replace=False)
    for i in idx:
        base_flat[i] += eps
        policy.set_flat(base_flat)
        loss_plus = _fast_loss(policy, batch)
        policy.set_flat(base_flat)
        base_flat[i] -= 2 * eps
        loss_minus = _fast_loss(policy, batch)
        policy.set_flat(base_flat)
        base_flat[i] += eps
        grad[i] = (loss_plus - loss_minus) / (2 * eps)
    return loss, grad


def _fast_loss(policy: MLP, batch: Dict[str, Any]) -> float:
    obs = batch['obs']
    actions = batch['actions']
    old_logp = batch['old_logp']
    advantages = batch['advantages']
    logits = policy.forward(obs)
    logits = np.asarray(logits)
    logits = logits - np.max(logits, axis=1, keepdims=True)
    exp_logits = np.exp(logits)
    probs = exp_logits / (np.sum(exp_logits, axis=1, keepdims=True) + 1e-8)
    log_probs = np.log(probs + 1e-8)
    new_logp = log_probs[np.arange(len(actions)), actions]
    ratio = np.exp(new_logp - old_logp)
    clipped = np.clip(ratio, 1.0 - 0.2, 1.0 + 0.2)
    policy_loss = -np.minimum(ratio * advantages, clipped * advantages).mean()
    entropy = -np.sum(probs * np.log(probs + 1e-8), axis=1).mean()
    return float(policy_loss - ENT_COEF * entropy)


def train():
    policy = MLP()
    if policy.load(MODEL_PATH):
        print("Resumed policy from", MODEL_PATH)

    start = time.time()
    for update in range(1, UPDATES + 1):
        seed = random.randint(1, 10_000_000)
        batch = collect_rollout(policy, seed, ROLLOUT_LEN)
        loss, grad = loss_and_grad(policy, batch)
        if np.any(np.isnan(grad)) or np.any(np.isinf(grad)):
            print("Bad gradient, skipping update")
            continue
        flat = policy.flat() - LR * np.clip(grad, -1.0, 1.0)
        policy.set_flat(flat)
        policy.save(MODEL_PATH)

        elapsed = time.time() - start
        eta = (elapsed / update) * max(UPDATES - update, 0)
        print(f"update {update:03d}/{UPDATES} | loss={loss:.4f} | "
              f"winner={batch['winner']} | steps={update * ROLLOUT_LEN} | "
              f"elapsed={elapsed/60:.1f}min eta={eta/60:.1f}min")

        if elapsed > 3.8 * 3600:
            print("Time budget nearly exhausted.")
            break

    print("Saved policy:", MODEL_PATH)


if __name__ == '__main__':
    train()
