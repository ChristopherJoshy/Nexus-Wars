import json
import sys
sys.path.insert(0, "test-bots/personal_agent")
from chrisv99 import agent_fn

obs_json = """
{
  "step": 50,
  "player": 0,
  "angular_velocity": 0.035,
  "planets": [
    [0, 0, 45, 50, 2, 50, 10, 100, 100, 5],
    [1, 1, 55, 50, 2, 20, 10, 100, 100, 5],
    [2, -1, 50, 60, 2, 10, 5, 100, 100, 5]
  ],
  "fleets": []
}
"""

obs = json.loads(obs_json)
actions = agent_fn(obs)
print("Generated Actions:", actions)
