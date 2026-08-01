#!/usr/bin/env python3
"""Generate int8-quantized, gzip+base85-compressed weights for chris.py."""
import base64, gzip, io, json
import numpy as np

WEIGHTS_PATH = r"test-bots/personal_agent/submission2_extracted/rl_trainer/puffer/checkpoints/orbit_wars/kj9h2f36/0000000419561472_jax_weights.npz"
OUTPUT_PATH = r"test-bots/personal_agent/_WEIGHTS_B85.txt"

with np.load(WEIGHTS_PATH) as npz:
    raw = {k: npz[k].astype(np.float32) for k in npz.files}

# Drop unused
if "encoder.embeddings.tok_embeddings.weight" in raw:
    del raw["encoder.embeddings.tok_embeddings.weight"]

# Per-tensor symmetric int8 quantization
all_names = sorted(raw.keys())
all_int8 = []
all_scales = []
all_shapes = []
for name in all_names:
    arr = raw[name]
    if arr.size == 0:
        scale = 1.0
        q = arr.astype(np.int8)
    else:
        max_abs = float(np.max(np.abs(arr)))
        scale = max_abs / 127.0 if max_abs > 0 else 1.0
        q = np.clip(np.round(arr / scale), -127, 127).astype(np.int8)
    all_int8.append(q.ravel())
    all_scales.append(np.float32(scale))
    all_shapes.append(list(q.shape))

concat_q = np.concatenate(all_int8)
concat_scales = np.array(all_scales, dtype=np.float32)

# Pack: JSON metadata + raw int8 bytes
meta = {
    "names": all_names,
    "shapes": all_shapes,
    "n_arrays": len(all_names),
}
meta_bytes = json.dumps(meta).encode("utf-8")
data_bytes = concat_q.tobytes()

# Write as: length(meta) as 4-byte int + meta + raw data
buffer = bytearray()
buffer.extend(len(meta_bytes).to_bytes(4, "little"))
buffer.extend(meta_bytes)
buffer.extend(data_bytes)
buffer.extend(concat_scales.tobytes())

raw_size = len(buffer)
print(f"Raw packed size: {raw_size/1024/1024:.2f} MB")

# Compress
compressed = gzip.compress(bytes(buffer), 9)
print(f"Gzip size: {len(compressed)/1024/1024:.2f} MB")

# Encode
b85 = base64.b85encode(compressed).decode("ascii")
print(f"Base85+gzip size: {len(b85)/1024/1024:.2f} MB")
print(f"String length: {len(b85)} chars")

# Verify roundtrip
decoded = gzip.decompress(base64.b85decode(b85))
meta_len = int.from_bytes(decoded[:4], "little")
meta_str = decoded[4:4+meta_len].decode("utf-8")
meta_parsed = json.loads(meta_str)
offset = 4 + meta_len
scales = np.frombuffer(decoded[offset+len(data_bytes):], dtype=np.float32)
print(f"Roundtrip: {meta_parsed['n_arrays']} arrays, scales match: {bool(np.allclose(scales, all_scales))}")

with open(OUTPUT_PATH, "w") as f:
    f.write(b85)

print(f"\nWritten to {OUTPUT_PATH}")
