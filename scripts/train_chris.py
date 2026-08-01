#!/usr/bin/env python3
"""
train_chris.py — RL for chris.py: one-match-per-update, winner-only reward.

Macro-actions:
  0 = hold, 1 = expand, 2 = attack

Wraps chris.py's heuristic with an 3-way macro-action policy.
Trains with REINFORCE on full-match returns against a fixed opponent pool.
"""

from __future__ import annotations

import math, os, random, sys, time
from typing import Any, Dict, List

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'test-bots', 'personal_agent'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'services', 'worker', 'engine', 'nexus_wars'))
import chris as chris_mod
from run_match import InProcessRunner, run_match

TOTAL_ENV_STEPS = 120_000
ROLLOUT_LEN = 64
UPDATES = TOTAL_ENV_STEPS // ROLLOUT_LEN
LR = 2e-4
GAMMA = 0.99
ENT_COEF = 0.02
OBS_DIM = 48
HIDDEN = 192
NLAYERS = 3
MODEL_PATH = os.path.join(REPO_ROOT, 'test-bots', 'personal_agent', 'chris_rl_policy.npz')
SAVE_EVERY = 20
ACT_HOLD, ACT_EXPAND, ACT_ATTACK = 0, 1, 2


def encode_obs(obs: dict, me: int) -> np.ndarray:
    planets = obs.get("planets", [])
    fleets = obs.get("fleets", [])
    step = float(obs.get("step", 0)) / 500.0
    my = [p for p in planets if p[1] == me]
    enemy = [p for p in planets if p[1] != me and p[1] != -1]
    neutrals = [p for p in planets if p[1] == -1]
    my_ships = float(sum(p[5] for p in my)) / 200.0
    en_ships = float(sum(p[5] for p in enemy)) / 200.0
    my_prod = float(sum(p[6] for p in my)) / 60.0
    en_prod = float(sum(p[6] for p in enemy)) / 60.0
    my_out = float(sum(1 for f in fleets if f[1] == me))
    en_in = float(sum(1 for f in fleets if f[1] != me and f[1] != -1))
    avg_my_ships = float(sum(p[5] for p in my) / max(len(my), 1))
    avg_en_ships = float(sum(p[5] for p in enemy) / max(len(enemy), 1))
    feats = [
        step,
        float(obs.get("angular_velocity", 0.035)),
        float(len(my)), float(len(enemy)), float(len(neutrals)),
        my_ships, en_ships, my_prod, en_prod,
        float(len(fleets)), my_out, en_in,
        avg_my_ships / 100.0, avg_en_ships / 100.0,
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

    def forward(self, x: np.ndarray):
        acts = [x]
        z = np.maximum(0.0, x @ self.params['W1'] + self.params['b1'])
        acts.append(z)
        for i in range(2, NLAYERS + 1):
            z = np.maximum(0.0, z @ self.params[f'W{i}'] + self.params[f'b{i}'])
            acts.append(z)
        logits = z @ self.params['Wp'] + self.params['bp']
        return logits, acts

    def flat(self) -> np.ndarray:
        return np.concatenate([v.ravel() for v in self.params.values()])

    def set_flat(self, flat: np.ndarray):
        offset = 0
        for k in self.params:
            size = self.params[k].size
            self.params[k] = np.asarray(flat[offset:offset + size]).reshape(self.params[k].shape).astype(np.float32)
            offset += size

    def param_count(self) -> int:
        return sum(v.size for v in self.params.values())

    def save(self, path: str):
        np.savez(path, flat=self.flat(),
                 obs_dim=np.array([OBS_DIM]),
                 hidden=np.array([HIDDEN]),
                 nlayers=np.array([NLAYERS]))

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
    me = obs.get("player", 0)
    planets = obs.get("planets", [])
    if action == ACT_HOLD:
        neutral_ids = {p[0] for p in planets if p[1] == -1}
        return [a for a in base if len(a) > 2 and a[2] not in neutral_ids][:2]
    if action == ACT_ATTACK:
        enemy_ids = {p[0] for p in planets if p[1] != -1 and p[1] != me}
        return [a for a in base if len(a) > 2 and a[2] in enemy_ids][:3]
    # EXPAND: only neutrals
    neutral_ids = {p[0] for p in planets if p[1] == -1}
    expanded = []
    for a in base:
        if len(a) > 2 and a[2] in neutral_ids and a[0] in {p[0] for p in planets if p[1] == me}:
            expanded.append(a)
    return expanded[:3]


def _infer_target_id(obs: dict, action: List) -> int | None:
    planets = obs.get("planets", [])
    if not planets or len(action) < 2:
        return None
    sx = next((p[2] for p in planets if p[0] == action[0]), None)
    sy = next((p[3] for p in planets if p[0] == action[0]), None)
    if sx is None or sy is None:
        return None
    angle = float(action[1])
    tx = sx + math.cos(angle) * 1e9
    ty = sy + math.sin(angle) * 1e9
    best_id, best_d = None, 1e18
    for p in planets:
        if p[0] == action[0]:
            continue
        d = math.hypot(p[2] - tx, p[3] - ty)
        if d < best_d:
            best_d = d
            best_id = p[0]
    return best_id


def make_agent(policy: MLP, player: int):
    def agent(obs: dict) -> List[List]:
        try:
            x = encode_obs(obs, player)
            logits, _ = policy.forward(x.reshape(1, -1))
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


def backward_simple(policy: MLP, obs_x: np.ndarray, actions: np.ndarray,
                    advantages: np.ndarray) -> Dict[str, np.ndarray]:
    grads = {k: np.zeros_like(v) for k, v in policy.params.items()}
    B = obs_x.shape[0]
    logits_all, acts = policy.forward(obs_x)
    logits_all = np.asarray(logits_all)
    logits_all = logits_all - np.max(logits_all, axis=1, keepdims=True)
    exp_logits = np.exp(logits_all)
    probs = exp_logits / (np.sum(exp_logits, axis=1, keepdims=True) + 1e-8)
    log_probs_logits = np.log(probs + 1e-8)
    new_logp = log_probs_logits[np.arange(B), actions]
    advantage = advantages.reshape(-1, 1)
    entropy = -np.sum(probs * log_probs_logits, axis=1, keepdims=True)
    d_logits = (-advantage * (1 - probs[np.arange(B), actions].reshape(-1, 1))
                - ENT_COEF * (probs * (log_probs_logits + 1.0)))
    d_logits = d_logits / B
    z_last = acts[-1]
    grads['Wp'] = z_last.T @ d_logits
    grads['bp'] = np.sum(d_logits, axis=0)
    dz = d_logits @ policy.params['Wp'].T
    for i in reversed(range(1, NLAYERS + 1)):
        z_in = acts[i - 1]
        pre = z_in @ policy.params[f'W{i}'] + policy.params[f'b{i}']
        mask = (pre > 0.0).astype(np.float32)
        grads[f'W{i}'] = z_in.T @ (dz * mask)
        grads[f'b{i}'] = np.sum(dz * mask, axis=0)
        dz = (dz * mask) @ policy.params[f'W{i}'].T
    return grads


def collect_opponent_pool(policy: MLP) -> Dict[str, Any]:
    """Play one match against a random opponent from the pool."""
    opponent_names = ["random", "starter", "fortress", "viper", "chimera-np", "chimera"]
    opp_name = random.choice(opponent_names)
    my_player = random.randint(0, 1)
    try:
        from nexus_wars.agents import agents as builtin
        opp_agent = builtin.get(opp_name, builtin["random"])
    except Exception:
        opp_agent = None

    if my_player == 0:
        runners = [
            InProcessRunner(make_agent(policy, 0)),
            InProcessRunner(opp_agent if opp_agent else make_agent(policy, 0)),
        ]
    else:
        runners = [
            InProcessRunner(opp_agent if opp_agent else make_agent(policy, 0)),
            InProcessRunner(make_agent(policy, 1)),
        ]

    try:
        replay = run_match(
            runners,
            seed=random.randint(1, 10_000_000),
            config={"episodeSteps": 500},
        )
    except Exception as e:
        print("match error", e)
        return None

    winner = replay.get("info", {}).get("winner", -1)
    steps_data = replay.get("steps", [])
    obs_list: List[np.ndarray] = []
    act_list: List[int] = []
    rew_list: List[float] = []

    for step_data in steps_data:
        obs0 = step_data.get("observation", {})
        for player, ob in enumerate((obs0, dict(obs0, player=1))):
            x = encode_obs(ob, player)
            logits, _ = policy.forward(x.reshape(1, -1))
            logits = np.asarray(logits).reshape(-1)
            logits = logits - np.max(logits)
            probs = np.exp(logits)
            probs = probs / (np.sum(probs) + 1e-8)
            action = int(np.random.choice(len(probs), p=probs))
            reward = -0.005
            my_ships = sum(p[5] for p in ob.get("planets", []) if p[1] == player)
            en_ships = sum(p[5] for p in ob.get("planets", []) if p[1] != player and p[1] != -1)
            reward += (my_ships - en_ships) * 0.0005
            obs_list.append(x)
            act_list.append(action)
            rew_list.append(reward)

    # terminal rewards
    for i in range(len(act_list)):
        player = i % 2
        if winner == player:
            rew_list[i] += 1.0
        elif winner != -1:
            rew_list[i] -= 1.0

    returns = np.zeros(len(rew_list), dtype=np.float32)
    R = 0.0
    for t in reversed(range(len(rew_list))):
        R = rew_list[t] + GAMMA * R
        returns[t] = R
    advantages = returns - returns.mean()
    advantages = advantages / (advantages.std() + 1e-8)

    return {
        'obs': np.stack(obs_list),
        'actions': np.array(act_list, dtype=np.int64),
        'advantages': advantages,
        'returns': returns,
        'winner': winner,
        'steps': len(steps_data),
        'opponent': opp_name,
        'my_player': my_player,
    }


def train():
    policy = MLP()
    if policy.load(MODEL_PATH):
        print("Resumed from", MODEL_PATH, "params:", policy.param_count())
    else:
        print("Fresh policy with", policy.param_count(), "params")

    start = time.time()
    for update in range(1, UPDATES + 1):
        batch = collect_opponent_pool(policy)
        if batch is None or len(batch['actions']) == 0:
            print("empty batch at update", update)
            continue

        grads = backward_simple(policy, batch['obs'], batch['actions'], batch['advantages'])
        for k in grads:
            g = np.clip(grads[k], -5.0, 5.0)
            policy.params[k] = policy.params[k] - LR * g

        if update % SAVE_EVERY == 0 or update == 1:
            policy.save(MODEL_PATH)

        elapsed = time.time() - start
        wr = 1.0 if batch['winner'] == 0 else 0.0 if batch['winner'] == 1 else 0.5
        eta = (elapsed / update) * max(UPDATES - update, 0)
        print(f"update {update:04d}/{UPDATES} vs={batch['opponent']} P{batch['my_player']} "
              f"wr={wr:.2f} steps={batch['steps']} n={len(batch['actions'])} | "
              f"elapsed={elapsed/60:.1f}min eta={eta/60:.1f}min")

        if elapsed > 3.8 * 3600:
            print("Time budget nearly exhausted.")
            break

    policy.save(MODEL_PATH)
    print("Saved final policy:", MODEL_PATH)


if __name__ == '__main__':
    train()
