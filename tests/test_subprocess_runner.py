"""End-to-end check of the subprocess bot runner path used by jobs.py.

Runs a real sample bot (written to a temp dir and executed as a subprocess
over the JSON-line protocol) against the built-in 'random' agent, and asserts
the match completes and the bot's actions are accepted by the engine.
"""
import json
import os
import sys
import tempfile

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "services", "worker", "engine", "nexus_wars")
sys.path.insert(0, ENGINE_DIR)

from run_match import run_match, make_runner, DEFAULT_CONFIG  # noqa: E402


SAMPLE_BOT = '''
import sys, json, math

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        obs = json.loads(line)
        step = obs.get("step", 0)
        if step == 0:
            sys.stdout.write(json.dumps([]) + "\\n")
            sys.stdout.flush()
            continue
        planets = obs["planets"]
        actions = []
        enemies = [e for e in planets if e[1] != obs["player"]]
        for p in planets:
            if p[1] != obs["player"]:  # only MY planets launch
                continue
            if not enemies:
                continue
            tgt = enemies[0]  # launch toward first enemy/neutral planet
            dx, dy = tgt[2] - p[2], tgt[3] - p[3]
            angle = math.atan2(dy, dx)
            if p[5] > 1:
                actions.append([p[0], angle, max(1, p[5] // 2)])
        sys.stdout.write(json.dumps(actions) + "\\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
'''


def _write_bot(d):
    path = os.path.join(d, "main.py")
    with open(path, "w") as f:
        f.write(SAMPLE_BOT)
    return path


def test_subprocess_vs_random():
    d = tempfile.mkdtemp()
    entry = _write_bot(d)
    runner_a = make_runner({"command": [sys.executable, entry],
                            "actTimeout": 2.0, "sandbox": None})
    runner_b = make_runner("random")
    replay = run_match([runner_a, runner_b], DEFAULT_CONFIG, seed=42)

    assert replay["info"]["steps"] >= 1, "match produced no steps"
    assert not runner_a.dead, "bot subprocess died unexpectedly"
    # at least one step should contain a non-empty action from our bot (player 0)
    saw_action = any(step.get("action") and step["action"][0]
                     for step in replay["steps"])
    assert saw_action, "bot never issued a launch"
    print(f"subprocess match OK: {replay['info']['steps']} steps, "
          f"winner={replay['info']['winner']}")


if __name__ == "__main__":
    test_subprocess_vs_random()
