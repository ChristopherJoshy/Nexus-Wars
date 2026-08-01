import numpy as np
import sys, json, os
sys.path.insert(0, '.')
sys.path.insert(0, 'test-bots/personal_agent')
sys.path.insert(0, 'services/worker/engine/nexus_wars')

# Check if ES weights exist
es_path = 'test-bots/personal_agent/_es_evaluator_b64.txt'
if os.path.exists(es_path):
    with open(es_path) as f:
        w = json.loads(f.read())
    print('ES weights found:')
    print('W1[0][:3]:', [round(float(x), 4) for x in w['W1'][0][:3]])
    print('W1 shape:', len(w['W1']), 'x', len(w['W1'][0]))
else:
    print('No ES weights found')

# Check baseline v7 weights
import chris
print()
print('v7 weights:')
print('W1[0][:3]:', [round(float(x), 4) for x in chris.W1[0][:3]])
