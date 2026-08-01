import numpy as np

w = np.load('test-bots/personal_agent/submission2_extracted/rl_trainer/puffer/checkpoints/orbit_wars/kj9h2f36/0000000419561472_jax_weights.npz', allow_pickle=True)
print(f'{len(w.files)} arrays, {sum(w[k].nbytes for k in w.files)/1e6:.1f} MB total')
for k in sorted(w.files):
    print(f'{k}: {w[k].shape} {w[k].dtype}')
