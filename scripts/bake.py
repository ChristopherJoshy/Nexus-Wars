"""
bake.py - Embed trained weights into chris.py to create a single-file agent.

Usage:
    python scripts/bake.py
    # Loads test-bots/personal_agent/chris_rl_policy.npz
    # Writes test-bots/personal_agent/chris.py with base64-encoded weights
"""

import base64
import io
import os
import sys

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def encode_weights(path: str) -> str:
    data = np.load(path)
    buf = io.BytesIO()
    np.savez(buf, **{k: data[k] for k in data.files})
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('ascii')


HEADER = '''#!/usr/bin/env python3
"""
Chris - Nexus Wars Supreme Champion Agent v8.

v8: RL-trained macro-action policy (~84k params) modulates v7 heuristic.
  - Macro-action selection: HOLD (defence only), EXPAND (neutrals only), ATTACK (enemies only)
  - Trained via REINFORCE against opponent pool
  - Weights baked into this single file as base64

v7 heuristic preserved: orbital prediction, sun avoidance, sniping,
coordinated strikes, energy management, neural evaluator.
"""

import base64
import io
import json
import math
import sys
from typing import Any, Dict, List, Tuple

import numpy as np

# ═══ Embedded RL policy weights ═══
CHRIS_WEIGHTS_B64 = """WEIGHTS_PLACEHOLDER"""

def _load_weights():
    raw = base64.b64decode(CHRIS_WEIGHTS_B64)
    return dict(np.load(io.BytesIO(raw)))

OBS_DIM = 48
HIDDEN = 192
N_HIDDEN_LAYERS = 3

def _encode_obs(obs, me):
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
    avg_my = float(sum(p[5] for p in my) / max(len(my), 1))
    avg_en = float(sum(p[5] for p in enemy) / max(len(enemy), 1))
    feats = [step, float(obs.get("angular_velocity", 0.035)),
             float(len(my)), float(len(enemy)), float(len(neutrals)),
             my_ships, en_ships, my_prod, en_prod,
             float(len(fleets)), my_out, en_in, avg_my / 100.0, avg_en / 100.0]
    while len(feats) < OBS_DIM:
        feats.append(0.0)
    return np.array(feats[:OBS_DIM], dtype=np.float32)

class _Policy:
    def __init__(self, weights):
        self.params = weights
    def act(self, obs, me):
        x = _encode_obs(obs, me).reshape(1, -1)
        z = np.maximum(0.0, x @ self.params["W1"] + self.params["b1"])
        for i in range(2, N_HIDDEN_LAYERS + 1):
            z = np.maximum(0.0, z @ self.params["W" + str(i)] + self.params["b" + str(i)])
        logits = z @ self.params["Wp"] + self.params["bp"]
        logits = np.asarray(logits).reshape(-1)
        logits = logits - np.max(logits)
        probs = np.exp(logits)
        probs = probs / (np.sum(probs) + 1e-8)
        return int(np.random.choice(len(probs), p=probs))

_POLICY = _Policy(_load_weights())
_MACRO_HOLD, _MACRO_EXPAND, _MACRO_ATTACK = 0, 1, 2

'''

HEURISTIC_START = "# ═══ Heuristic engine v7"
HEURISTIC_END = "# ═══ Agent entrypoint"


def build_single_file(weights_b64: str, heuristic_code: str) -> str:
    macro_code = '''
# ═══ Macro-action helpers ═══
def _infer_target_id(obs, action):
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

def _apply_macro(obs, action, base):
    me = obs.get("player", 0)
    planets = obs.get("planets", [])
    if action == _MACRO_HOLD:
        neutrals = {p[0] for p in planets if p[1] == -1}
        out = []
        for a in base:
            if len(a) < 2:
                continue
            tid = _infer_target_id(obs, a)
            if tid is None or tid in neutrals:
                continue
            out.append(a)
        return out
    if action == _MACRO_ATTACK:
        enemy_ids = {p[0] for p in planets if p[1] != -1 and p[1] != me}
        out = []
        for a in base:
            if len(a) < 2:
                continue
            tid = _infer_target_id(obs, a)
            if tid is not None and tid in enemy_ids:
                out.append(a)
        return out or base
    neutral_ids = {p[0] for p in planets if p[1] == -1}
    out = []
    for a in base:
        if len(a) < 2:
            continue
        tid = _infer_target_id(obs, a)
        if tid is not None and tid in neutral_ids:
            out.append(a)
    return out

# ═══ Agent entrypoint ═══
def agent_fn(obs):
    try:
        me = int(obs.get("player", 0))
        macro = _POLICY.act(obs, me)
    except Exception:
        macro = _MACRO_HOLD
    base = _run_heuristic(obs)
    return _apply_macro(obs, macro, base)

if __name__ == "__main__":
    for line in sys.stdin:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            obs = json.loads(line_str)
            sys.stdout.write(json.dumps(agent_fn(obs)) + "\\n")
            sys.stdout.flush()
        except Exception:
            sys.stdout.write("[]\\n")
            sys.stdout.flush()
'''

    header = HEADER.replace('WEIGHTS_PLACEHOLDER', weights_b64)
    return header + heuristic_code + macro_code


def main():
    weights_path = os.path.join(REPO_ROOT, 'test-bots', 'personal_agent', 'chris_rl_policy.npz')
    if not os.path.exists(weights_path):
        print("Missing weights:", weights_path)
        sys.exit(1)

    chris_path = os.path.join(REPO_ROOT, 'test-bots', 'personal_agent', 'chris.py')
    with open(chris_path, 'r') as f:
        chris_content = f.read()

    # Extract heuristic code (between the constants and the agent entrypoint)
    lines = chris_content.split('\n')
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if 'BOARD_SIZE' in line and '=' in line:
            start_idx = i
        if '__name__' in line:
            end_idx = i
            break

    if start_idx is None:
        start_idx = 0
    if end_idx is None:
        end_idx = len(lines)

    heuristic_code = '\n'.join(lines[start_idx:end_idx])

    b64 = encode_weights(weights_path)
    print("Weight payload length:", len(b64))
    single_file = build_single_file(b64, heuristic_code)
    print("Estimated .py size:", len(single_file), "bytes")

    with open(chris_path, 'w', encoding='utf-8') as f:
        f.write(single_file)
    print("Wrote:", chris_path)


if __name__ == '__main__':
    main()
