#!/usr/bin/env python3
import os, sys, time
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, 'scripts')
import train_chris as tc

p = tc.MLP()
t0 = time.time()
seen = set()
for i in range(10):
    b = tc.collect_rollouts_opponent_pool(p, 64)
    g = tc.backward_simple(p, b['obs'], b['actions'], b['advantages'])
    for k in g:
        g[k] = g[k].clip(-5.0, 5.0)
        p.params[k] = p.params[k] - 3e-4 * g[k]
    w = b['winner']
    win = 1 if w == 0 else 0 if w == 1 else 0.5
    seen.add(w)
    print(f'{i} wr={win} winner={w} n={len(b["actions"])} time={time.time()-t0:.1f}s')
    if i % 5 == 0:
        p.save('train_opp.npz')
p.save('train_opp.npz')
print('params', p.param_count(), 'unique winners', seen)
