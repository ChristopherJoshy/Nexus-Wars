import numpy as np
import sys

path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/orbit_wars_dl/weight.npz'
with np.load(path) as f:
    print('Keys:', sorted(f.files))
    print('Total keys:', len(f.files))
    total = 0
    for k in sorted(f.files):
        arr = f[k]
        total += arr.size
        print(f'  {k}: shape={arr.shape}, dtype={arr.dtype}, params={arr.size}')
    print(f'Total params: {total:,}')
