"""
Nexus Wars engine test suite.

Run:  python3 tests/test_nexus_wars.py
(or:  python3 -m pytest tests/test_nexus_wars.py -q)

Covers:
  * regression of the Orbit-Wars bug classes (race/erasure, geometric
    tunneling, multi-attacker summation, step-default, off-by-one
    termination, X/Y coordinate swap, OOB-before-collision).
  * the new energy system (launch cost, clean rejection, regen cap).
  * determinism (same seed => byte-identical replay).
"""

import math
import os
import sys
import json

ENGINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "services", "worker", "engine", "nexus_wars")
sys.path.insert(0, ENGINE_DIR)

from nexus_wars import (interpreter, Planet, BOARD_SIZE, CENTER, SUN_RADIUS,
                        ROTATION_RADIUS_LIMIT, DEFAULT_LAUNCH_ENERGY_COST)
from run_match import run_match, make_runner, make_env, _build_state, DEFAULT_CONFIG


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def init_state(seed=1, num_agents=2, config=None):
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)
    cfg["seed"] = seed
    env = make_env(cfg)
    state = _build_state(num_agents)
    interpreter(state, env)  # init
    return state, env


def find_home(state, player):
    for p in state[0].observation.planets:
        if p[1] == player:
            return p
    return None


def step_once(state, env, actions):
    for i, a in enumerate(actions):
        state[i].action = a
    state[0].observation.step = getattr(state[0].observation, "step", 0)
    interpreter(state, env)
    state[0].observation.step = (state[0].observation.step or 0) + 1


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
def test_full_game_completes():
    runners = [make_runner("random"), make_runner("starter")]
    replay = run_match(runners, {"seed": 7}, seed=7)
    assert 1 <= replay["info"]["steps"] <= 500, replay["info"]["steps"]
    assert len(replay["info"]["scores"]) == 2
    assert replay["info"]["winner"] in (0, 1, None)
    print("PASS test_full_game_completes")


def test_determinism():
    def det(obs):
        moves = []
        me = obs["player"]
        for p in obs["planets"]:
            if p[1] == me and p[5] >= 20:
                moves.append([p[0], 0.0, p[5] // 2])
        return moves

    r1 = run_match([make_runner(det), make_runner(det)], {"seed": 42}, seed=42)
    r2 = run_match([make_runner(det), make_runner(det)], {"seed": 42}, seed=42)
    assert json.dumps(r1["steps"]) == json.dumps(r2["steps"]), "replay not deterministic"
    print("PASS test_determinism")


def test_coordinate_angle_zero_moves_right():
    state, env = init_state(seed=3)
    home = find_home(state, 0)
    assert home is not None
    pid, hx, hy, r = home[0], home[2], home[3], home[4]
    step_once(state, env, [[[pid, 0.0, 5]], []])  # launch 5 ships at angle 0
    fleet = next((f for f in state[0].observation.fleets if f[1] == 0), None)
    assert fleet is not None, "no fleet launched"
    launch_x = hx + (r + 0.1)
    # angle 0 => +x (right); fleet moved further right, y unchanged.
    assert fleet[2] > launch_x, f"fleet x did not increase: {fleet[2]} vs {launch_x}"
    assert abs(fleet[3] - hy) < 1e-9, f"fleet y moved on angle 0: {fleet[3]} vs {hy}"
    print("PASS test_coordinate_angle_zero_moves_right")


def test_energy_launch_cost():
    # Insufficient energy => clean rejection (no fleet, ships unchanged).
    # Disable production (set to 0) so we isolate the launch effect.
    state, env = init_state(seed=5)
    home = find_home(state, 0)
    home[6] = 0  # production = 0
    home[9] = 0  # energy regen = 0 (isolate the launch cost)
    home[7] = 0  # energy = 0
    ships_before = home[5]
    step_once(state, env, [[[home[0], 0.0, 5]], []])
    fleets = [f for f in state[0].observation.fleets if f[1] == 0]
    assert len(fleets) == 0, "fleet launched despite insufficient energy"
    assert home[5] == ships_before, "ships changed on rejected launch"

    # Sufficient energy => launch, energy & ships deducted by cost.
    home[6] = 0  # keep production off
    home[9] = 0  # keep regen off
    home[7] = 100
    e_before, s_before = home[7], home[5]
    step_once(state, env, [[[home[0], 0.0, 5]], []])
    fleets = [f for f in state[0].observation.fleets if f[1] == 0]
    assert len(fleets) == 1, "fleet not launched with sufficient energy"
    assert home[5] == s_before - 5
    assert home[7] == e_before - DEFAULT_LAUNCH_ENERGY_COST
    print("PASS test_energy_launch_cost")


def test_energy_regen_caps():
    state, env = init_state(seed=9)
    p = state[0].observation.planets[0]
    p[1] = 0
    p[7] = p[8]  # already at cap
    step_once(state, env, [[], []])
    assert p[7] <= p[8], "energy exceeded cap"
    assert p[7] == p[8], "energy regen overflowed cap"
    print("PASS test_energy_regen_caps")


def test_termination_resolves_last_step():
    # Two passive agents never eliminate each other => full 500 steps,
    # including the final step (no off-by-one truncation).
    def passive(obs):
        return []

    replay = run_match([make_runner(passive), make_runner(passive)],
                       {"seed": 11, "episodeSteps": 500}, seed=11)
    assert replay["info"]["steps"] == 500, replay["info"]["steps"]
    last = replay["steps"][-1]
    assert last["observation"]["step"] == 499, last["observation"]["step"]
    print("PASS test_termination_resolves_last_step")


def test_no_comets():
    state, env = init_state(seed=2)
    obs = state[0].observation
    assert not hasattr(obs, "comets"), "comets present"
    assert "comet_planet_ids" not in obs.__dict__, "comet ids present"
    assert len(obs.planets) > 0
    print("PASS test_no_comets")


def test_multi_attacker_sum():
    state, env = init_state(seed=4)
    obs0 = state[0].observation
    # Inject a neutral planet at a static position (off the rotation band).
    test_planet = [999, -1, 50.0, 85.0, 5.0, 0, 1, 0, 100, 5]
    obs0.planets.append(test_planet)
    obs0.initial_planets.append(list(test_planet))
    # Two player-0 fleets converging on it (angle = +y towards the planet).
    obs0.fleets.append([1000, 0, 50.0, 80.0, math.pi / 2, -1, 10, 0])
    obs0.fleets.append([1001, 0, 50.0, 80.3, math.pi / 2, -1, 7, 0])
    step_once(state, env, [[], []])
    tp = next(p for p in obs0.planets if p[0] == 999)
    assert tp[1] == 0, f"planet not captured by player 0: owner={tp[1]}"
    assert tp[5] == 10 + 7, f"fleets not summed: ships={tp[5]}"
    print("PASS test_multi_attacker_sum")


def test_collision_before_oob():
    # A fleet whose path passes through a planet but whose endpoint lands
    # out of bounds must still be captured (planet collision checked first).
    state, env = init_state(seed=6)
    obs0 = state[0].observation
    planet = [998, -1, 97.0, 50.0, 5.0, 0, 1, 0, 100, 5]
    obs0.planets.append(planet)
    obs0.initial_planets.append(list(planet))
    # Starts at (94,50), angle 0, speed 6 -> endpoint (100,50) which is OOB,
    # but the path passes through the planet at x=97.
    obs0.fleets.append([1002, 0, 94.0, 50.0, 0.0, -1, 12, 0])
    step_once(state, env, [[], []])
    tp = next(p for p in obs0.planets if p[0] == 998)
    assert tp[1] == 0, "edge fleet destroyed by OOB instead of captured"
    assert tp[5] == 12, "captured fleet ships not applied"
    assert all(f[0] != 1002 for f in obs0.fleets), "captured fleet not removed"
    print("PASS test_collision_before_oob")


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------
def _main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # pragma: no cover
            failed += 1
            print(f"ERROR {t.__name__}: {repr(e)}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
