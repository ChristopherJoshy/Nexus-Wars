#!/usr/bin/env python3
import train_chris as tc
import time, os
os.environ['SDL_VIDEODRIVER']='dummy'
t0=time.time()
p=tc.MLP()
steps=0
for i in range(20):
    b=tc.collect_rollouts(p,64)
    g=tc.backward_simple(p,b['obs'],b['actions'],b['advantages'])
    for k in g:
        g[k]=g[k].clip(-5,5)
        p.params[k]-=1e-4*g[k]
    steps+=len(b['actions'])
    dt=time.time()-t0
    print(f"{i:02d} n={len(b['actions'])} steps={steps} time={dt:.1f}s sps={steps/dt:.1f}")
print(f'Total params: {p.param_count()}')
p.save('test_rl_policy.npz')
