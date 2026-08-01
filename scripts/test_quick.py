#!/usr/bin/env python3
import os, sys, time
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, 'scripts')
import train_chris as tc

p = tc.MLP()
t0 = time.time()
for i in range(5):
    b = tc.collect_opponent_pool(p)
    g = tc.backward_simple(p, b['obs'], b['actions'], b['advantages'])
    for k in g:
        g[k] = g[k].clip(-5.0, 5.0)
        p.params[k] = p.params[k] - 2e-4 * g[k]
    w = b['winner']
    wr = 1.0 if w == 0 else 0.0 if w == 1 else 0.5
    print(f'{i} vs={b["opponent"]} P{b["my_player"]} wr={wr} steps={b["steps"]} n={len(b["actions"])} time={time.time()-t0:.1f}s')
print('params', p.param_count())
