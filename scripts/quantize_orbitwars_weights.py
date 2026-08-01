#!/usr/bin/env python3
"""Quantize orbit-wars weights to int8 and package as base64+gzip for embedding."""
import base64, gzip, io, json
import numpy as np

WEIGHTS_PATH = r"C:\Users\chris\Documents\Work\Nexus\Nexus Wars\test-bots\personal_agent\submission2_extracted\rl_trainer\puffer\checkpoints\orbit_wars\kj9h2f36\0000000419561472_jax_weights.npz"

# Load all arrays
with np.load(WEIGHTS_PATH) as npz:
    raw = {k: npz[k].astype(np.float32) for k in npz.files}

print(f"Loaded {len(raw)} arrays, total float32 bytes: {sum(v.nbytes for v in raw.values())/1024/1024:.1f} MB")

# Per-tensor symmetric int8 quantization
quantized = {}
for name, arr in raw.items():
    if arr.ndim == 0 or arr.size == 0:
        quantized[name] = {"q": arr.astype(np.int8), "scale": np.float32(1.0), "shape": arr.shape, "dtype": "skip"}
        continue
    max_abs = float(np.max(np.abs(arr)))
    if max_abs == 0:
        scale = 1.0
    else:
        scale = max_abs / 127.0
    q = np.clip(np.round(arr / scale), -127, 127).astype(np.int8)
    quantized[name] = {
        "q": q,
        "scale": np.float32(scale),
        "shape": q.shape,
    }

# Verify quantization error
max_err = 0.0
for name, info in quantized.items():
    deq = info["q"].astype(np.float32) * info["scale"]
    err = float(np.max(np.abs(deq - raw[name])))
    max_err = max(max_err, err)
print(f"Max quantization error: {max_err:.6f}")

# Package: store as compressed npz
buf = io.BytesIO()
np.savez_compressed(buf, **{k + ".q": v["q"] for k, v in quantized.items()},
                    **{k + ".scale": v["scale"] for k, v in quantized.items()},
                    **{k + ".shape": np.array(v["shape"]) for k, v in quantized.items()})
raw_np = buf.getvalue()
print(f"npz_compressed size: {len(raw_np)/1024/1024:.1f} MB")

gz = gzip.compress(raw_np, 9)
print(f"gzip size: {len(gz)/1024/1024:.1f} MB")

b64 = base64.b64encode(gz).decode("ascii")
print(f"base64+gzip size: {len(b64)/1024/1024:.1f} MB")
print(f"base64 string length: {len(b64)} chars")

# Also try: just store int8 + scales more efficiently
# Store as a single concatenated int8 array + scales array
all_names = sorted(quantized.keys())
all_q = np.concatenate([quantized[n]["q"].ravel() for n in all_names])
all_scales = np.array([quantized[n]["scale"] for n in all_names], dtype=np.float32)
all_shapes = [quantized[n]["shape"] for n in all_names]
offsets = []
off = 0
for n in all_names:
    sz = quantized[n]["q"].size
    offsets.append((n, all_shapes[len(offsets)], off, sz))
    off += sz

buf2 = io.BytesIO()
np.savez_compressed(buf2, q=all_q, scales=all_scales, names=np.array(all_names), 
                    offsets=np.array([[o[2], o[3]] for o in offsets]))
raw2 = buf2.getvalue()
gz2 = gzip.compress(raw2, 9)
b64_2 = base64.b64encode(gz2).decode("ascii")
print(f"\nConcatenated approach:")
print(f"  int8 data: {all_q.nbytes/1024/1024:.1f} MB")
print(f"  npz_compressed: {len(raw2)/1024/1024:.1f} MB")
print(f"  gzip: {len(gz2)/1024/1024:.1f} MB")
print(f"  base64+gzip: {len(b64_2)/1024/1024:.1f} MB")
