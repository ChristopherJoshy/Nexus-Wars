import json
import sys
sys.path.insert(0, '/app/engine')
from nexus_wars import interpreter, Planet, Fleet, BOARD_SIZE, CENTER, SUN_RADIUS
from nexus_wars.run_match import make_env, _build_state, serialize_observation
env = make_env({'episodeSteps': 500, 'seed': 1234})
state = _build_state(2)
interpreter(state, env)
obs0 = state[0].observation
obs_dict = serialize_observation(obs0)
obs_dict['player'] = 0
obs_dict['step'] = 0
print(json.dumps(obs_dict))
