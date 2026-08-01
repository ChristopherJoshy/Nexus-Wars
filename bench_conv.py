import numpy as np
import time

N, C_in, T = 800, 128, 20
C_out, K = 128, 5
padding = K // 2

x = np.random.randn(N, C_in, T).astype(np.float32)
weight = np.random.randn(C_out, C_in, K).astype(np.float32)
bias = np.random.randn(C_out).astype(np.float32)

# Approach 1: im2col + matmul
start = time.perf_counter()
padded = np.pad(x, ((0,0),(0,0),(padding,padding)), mode="constant")
cols = np.lib.stride_tricks.sliding_window_view(padded, K, axis=2)
cols = cols.transpose(1,3,0,2).reshape(C_in*K, N*T)
w = weight.reshape(C_out, C_in*K)
output = (w @ cols).reshape(C_out, N, T).transpose(1,0,2)
output += bias[np.newaxis, :, np.newaxis]
elapsed = time.perf_counter() - start
print("im2col+matmul: %.1f ms" % (elapsed*1000))

# Approach 2: loop over kernel
start = time.perf_counter()
padded = np.pad(x, ((0,0),(0,0),(padding,padding)), mode="constant")
out2 = np.zeros((N, C_out, T), dtype=np.float32)
for k in range(K):
    inp = padded[:, :, k:k+T]
    inp_col = inp.transpose(1,0,2).reshape(C_in, N*T)
    out2 += (weight[:,:,k] @ inp_col).reshape(C_out, N, T).transpose(1,0,2)
out2 += bias[np.newaxis, :, np.newaxis]
elapsed = time.perf_counter() - start
print("kernel loop+matmul: %.1f ms" % (elapsed*1000))

# Approach 3: tensordot
start = time.perf_counter()
cols3 = np.lib.stride_tricks.sliding_window_view(padded, K, axis=2)
out3 = np.tensordot(cols3, weight, axes=([1,3],[1,2])).transpose(2,0,1)
out3 += bias[np.newaxis, :, np.newaxis]
elapsed = time.perf_counter() - start
print("tensordot: %.1f ms" % (elapsed*1000))

# Full model timing
start = time.perf_counter()
# Conv block 0: 10->128
padded = np.pad(x, ((0,0),(0,0),(2,2)), mode="constant")
cols = np.lib.stride_tricks.sliding_window_view(padded, 5, axis=2)
cols = cols.transpose(1,3,0,2).reshape(50, N*T)
w0 = np.random.randn(128, 50).astype(np.float32)
y = (w0 @ cols).reshape(128, N, T).transpose(1,0,2)
y += bias[np.newaxis, :, np.newaxis]
# 3 more blocks 128->128
for i in range(3):
    w = np.random.randn(128, 640).astype(np.float32)
    padded = np.pad(y, ((0,0),(0,0),(2,2)), mode="constant")
    cols = np.lib.stride_tricks.sliding_window_view(padded, 5, axis=2)
    cols = cols.transpose(1,3,0,2).reshape(640, N*T)
    y = (w @ cols).reshape(128, N, T).transpose(1,0,2)
    y += bias[np.newaxis, :, np.newaxis]
elapsed = time.perf_counter() - start
print("4 conv blocks (im2col): %.1f ms" % (elapsed*1000))

# Encoder: 7 layers, batch=1, seq=40, hidden=256
h = np.random.randn(1, 40, 256).astype(np.float32)
Wqkv = np.random.randn(768, 256).astype(np.float32)
Wo_att = np.random.randn(256, 256).astype(np.float32)
Wi = np.random.randn(768, 256).astype(np.float32)
Wo_mlp = np.random.randn(256, 384).astype(np.float32)

start = time.perf_counter()
for i in range(7):
    qkv = h @ Wqkv.T
    qkv = qkv.reshape(1, 40, 3, 4, 64)
    q = qkv[:, :, 0].transpose(0,2,1,3)
    k = qkv[:, :, 1].transpose(0,2,1,3)
    v = qkv[:, :, 2].transpose(0,2,1,3)
    scores = q @ k.transpose(0,1,3,2) * (1.0/np.sqrt(64))
    attn = np.exp(scores - scores.max(axis=-1, keepdims=True))
    attn = attn / attn.sum(axis=-1, keepdims=True)
    ao = (attn @ v).transpose(0,2,1,3).reshape(1,40,256)
    h = h + ao @ Wo_att.T
    wi_out = h @ Wi.T
    inp_gate = wi_out[..., :384]
    gate = wi_out[..., 384:]
    h = h + (np.maximum(0, inp_gate) * gate) @ Wo_mlp.T
elapsed = time.perf_counter() - start
print("7 encoder layers: %.1f ms" % (elapsed*1000))

# Target head
start = time.perf_counter()
q = h @ np.random.randn(256,256).astype(np.float32).T
k = h @ np.random.randn(256,256).astype(np.float32).T
q = q.reshape(1,40,4,64).transpose(0,2,1,3)
k = k.reshape(1,40,4,64).transpose(0,2,1,3)
scores = q @ k.transpose(0,1,3,2) / np.sqrt(64)
hw = np.exp(np.random.randn(4).astype(np.float32))
hw = hw / hw.sum()
logits = np.sum(scores * hw.reshape(1,4,1,1), axis=1)
elapsed = time.perf_counter() - start
print("target head: %.1f ms" % (elapsed*1000))

total = 200 + elapsed  # estimate conv at ~200ms, add encoder+head
print("Total estimated: %.1f ms" % total)
