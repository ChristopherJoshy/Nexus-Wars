#!/usr/bin/env python3
import os, sys, time, random
os.environ['SDL_VIDEODRIVER'] = 'dummy'
sys.path.insert(0, 'scripts')
import train_chris as tc

p = tc.MLP()
random.seed(42)
opponents = []
for _ in range(50):
    opp = random.choice(["random", "starter", "fortress", "viper", "chimera-np", "chimera"])
    b = tc.collect_opponent_pool(p)
    if b is None:
        continue
    w = b['winner']
    wr = 1.0 if w == 0 else 0.0 if w == 1 else 0.5
    if opp == "chimera":
        print(f'vs={opp} P{b["my_player"]} wr={wr} steps={b["steps"]} winner={w}')
    opponents.append((opp, b['my_player'], wr, w, b['steps']))

print("\nvs chimera summary:")
chim = [x for x in opponents if x[0] == "chimera"]
if chim:
    wins = sum(1 for o in chim if o[2] == 1.0)
    print(f"wins={wins} total={len(chim)}")
