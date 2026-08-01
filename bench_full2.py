import numpy as np
import time

np.random.seed(42)
HIDDEN = 256
T_MAX = 20
N_BODIES = 40

def gelu(x):
    return x * 0.5 * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x * x * x)))

def layer_norm(x, weight, bias, eps=1e-5):
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) * np.reciprocal(np.sqrt(var + eps)) * weight + bias

def conv1d(x_nct, weight, bias, padding):
    """x_nct: (N, C_in, T), weight: (C_out, C_in, K), bias: (C_out,)"""
    N, Cin, Tlen = x_nct.shape
    Cout, _, K = weight.shape
    padded = np.pad(x_nct, ((0,0),(0,0),(padding,padding)), constant_values=0)
    out = np.zeros((N, Cout, Tlen), dtype=np.float32)
    for k in range(K):
        inp = padded[:, :, k:k+Tlen]  # (N, Cin, T)
        out += np.matmul(weight[:, :, k], inp.transpose(1, 0, 2).reshape(Cin, N * Tlen)).reshape(Cout, N, T).transpose(1, 0, 2)
    return out + bias[np.newaxis, :, np.newaxis]

# Input: [1, 40, 20, 10] -> reshape to (800, 10, 20) NCT
x_input = np.random.randn(1, 40, 20, 10).astype(np.float32)
body_mask = np.ones((1, 40), dtype=np.float32)

start = time.perf_counter()

batch_size, n_bodies, n_timesteps, input_dim = 1, 40, 20, 10
y = x_input.reshape(batch_size * n_bodies, n_timesteps, input_dim)  # (800, 20, 10) NTC
y_nct = y.transpose(0, 2, 1)  # (800, 10, 20) NCT
block_mask = body_mask[0].reshape(batch_size * n_bodies)  # (800,)
block_mask_3d = block_mask[:, np.newaxis, :]  # (800, 1, 1) broadcast

# Conv block 0: 10->128 with residual conv
w0 = np.random.randn(128, 10, 5).astype(np.float32) * 0.1678
b0 = np.random.randn(128).astype(np.float32)
rw0 = np.random.randn(128, 10, 1).astype(np.float32)
rb0 = np.random.randn(128).astype(np.float32)
lnw0 = np.ones(128, dtype=np.float32)
lnb0 = np.zeros(128, dtype=np.float32)

t0 = time.perf_counter()
c = conv1d(y_nct, w0, b0, 2)
r = conv1d(y_nct, rw0, rb0, 0)
c = gelu(c + r) * block_mask_3d
# LayerNorm: (N, C, T) -> (N, T, C) -> norm
c_tc = c.transpose(0, 2, 1)
c_tc = layer_norm(c_tc, lnw0, lnb0)
c = c_tc.transpose(0, 2, 1)
t_conv0 = time.perf_counter() - t0

# Conv blocks 1-3
t1 = time.perf_counter()
for i in range(3):
    w = np.random.randn(128, 128, 5).astype(np.float32) * 0.1678
    b = np.random.randn(128).astype(np.float32)
    lnw = np.ones(128, dtype=np.float32)
    lnb = np.zeros(128, dtype=np.float32)
    c = conv1d(c, w, b, 2)
    c = gelu(c + c) * block_mask_3d  # residual: conv + previous = 2*c? No, residual add
    # Actually: y = gelu(conv) + residual (same as input to block)
    # But in the model, the residual is the OUTPUT of the previous block (not the conv output)
    # Wait, reading the model code again:
    # conv_block: residual = x; if residual_conv: residual = conv1d(x, ...); y = conv1d(x); y = gelu(y) + residual; y = layer_norm(y); return y
    # So y = gelu(conv(x)) + residual(x)
    # For block 1+: y = gelu(conv(x)) + x  (residual = x, no residual conv)
    pass
t_conv = time.perf_counter() - t1

# Fix: re-do conv blocks 1-3 properly
c = c_tc.transpose(0, 2, 1)  # restore
t1b = time.perf_counter()
for i in range(3):
    w = np.random.randn(128, 128, 5).astype(np.float32) * 0.1678
    b = np.random.randn(128).astype(np.float32)
    lnw = np.ones(128, dtype=np.float32)
    lnb = np.zeros(128, dtype=np.float32)
    prev = c
    c = conv1d(c, w, b, 2)
    c = gelu(c + prev) * block_mask_3d
    c_tc = c.transpose(0, 2, 1)
    c_tc = layer_norm(c_tc, lnw, lnb)
    c = c_tc.transpose(0, 2, 1)
t_conv = time.perf_counter() - t1b

# Global avg pool + output projection
t2 = time.perf_counter()
# c: (800, 128, 20) NCT -> reshape to (1, 40, 20, 128) NTC
emb_nct = c.reshape(1, 40, 20, 128).transpose(0, 1, 3, 2)  # wait no
# c is (800, 128, 20) = (N*C_in=800, C_out=128, T=20) in NCT
# We need (1, 40, T, 128) for masking
emb_ntc = c.transpose(0, 2, 1).reshape(1, 40, 20, 128)  # (1, 40, 20, 128)
valid4 = body_mask[:, :, np.newaxis, np.newaxis]  # (1, 40, 1, 1)
denom = np.maximum(body_mask[:, :, np.newaxis].sum(axis=2, keepdims=True), 1.0)  # (1, 40, 1)
emb = (emb_ntc * body_mask[:, :, np.newaxis, np.newaxis]).sum(axis=2) / denom  # (1, 40, 128)
first_ts = x_input[:, :, 0, :]  # (1, 40, 10)
emb = np.concatenate([emb, first_ts], axis=-1)  # (1, 40, 138)
w_o = np.random.randn(256, 138).astype(np.float32)
b_o = np.random.randn(256).astype(np.float32)
embeddings = emb @ w_o.T + b_o  # (1, 40, 256)
t_pool = time.perf_counter() - t2

# Encoder
t3 = time.perf_counter()
enc_norm_w = np.ones(256, dtype=np.float32)
hidden = layer_norm(embeddings, enc_norm_w, np.zeros(256, dtype=np.float32)) * body_mask[:, :, np.newaxis]

attn_mask = body_mask.astype(np.float32)  # (1, 40)
add_mask = np.where(attn_mask[:, np.newaxis, :, :], 0.0, -1e9)  # (1, 1, 40, 40)

for i in range(7):
    ai = np.ones(256, dtype=np.float32)
    Wqkv = np.random.randn(768, 256).astype(np.float32)
    Wo_att = np.random.randn(256, 256).astype(np.float32)
    mlp_norm_w = np.ones(256, dtype=np.float32)
    Wi = np.random.randn(768, 256).astype(np.float32)
    Wo_mlp = np.random.randn(256, 384).astype(np.float32)

    ai_input = hidden
    if i != 0:
        ai_input = layer_norm(ai_input, ai, np.zeros(256, dtype=np.float32))

    qkv = ai_input @ Wqkv.T
    qkv = qkv.reshape(1, 40, 3, 4, 64)
    q = qkv[:, :, 0].transpose(0, 2, 1, 3)  # (1, 4, 40, 64)
    k = qkv[:, :, 1].transpose(0, 2, 1, 3)
    v = qkv[:, :, 2].transpose(0, 2, 1, 3)
    scores = q @ k.transpose(0, 1, 3, 2) * (1.0 / np.sqrt(64))
    scores = scores + add_mask
    attn = np.exp(scores - scores.max(axis=-1, keepdims=True))
    attn = attn / attn.sum(axis=-1, keepdims=True)
    ao = (attn @ v).transpose(0, 2, 1, 3).reshape(1, 40, 256)
    attn_out = ao @ Wo_att.T
    hidden = hidden + attn_out

    mlp_in = layer_norm(hidden, mlp_norm_w, np.zeros(256, dtype=np.float32))
    wi_out = mlp_in @ Wi.T
    inp = wi_out[..., :384]
    gate = wi_out[..., 384:]
    mlp_out = gelu(inp) * gate @ Wo_mlp.T
    hidden = hidden + mlp_out

final_norm_w = np.ones(256, dtype=np.float32)
hidden = layer_norm(hidden, final_norm_w, np.zeros(256, dtype=np.float32))
t_enc = time.perf_counter() - t3

# Heads
t4 = time.perf_counter()
launch_w = np.random.randn(1, 256).astype(np.float32)
launch_b = np.zeros(1, dtype=np.float32)
tgt_q = np.random.randn(256, 256).astype(np.float32)
tgt_k = np.random.randn(256, 256).astype(np.float32)
tgt_hw = np.random.randn(4).astype(np.float32)

launch_logits = (hidden @ launch_w.T + launch_b).squeeze(-1)  # (1, 40)
launch_prob = 1.0 / (1.0 + np.exp(-launch_logits))

q = hidden @ tgt_q.T
k = hidden @ tgt_k.T
q = q.reshape(1, 40, 4, 64).transpose(0, 2, 1, 3)
k = k.reshape(1, 40, 4, 64).transpose(0, 2, 1, 3)
scores = q @ k.transpose(0, 1, 3, 2) / np.sqrt(64)
hw = np.exp(tgt_hw)
hw = hw / hw.sum()
target_logits = np.sum(scores * hw[np.newaxis, :, np.newaxis, np.newaxis], axis=1)
t_heads = time.perf_counter() - t4

total = time.perf_counter() - start
print("Conv block 0: %.1f ms" % (t_conv0 * 1000))
print("Conv blocks 1-3: %.1f ms" % (t_conv * 1000))
print("Pool+embed: %.1f ms" % (t_pool * 1000))
print("7 encoder layers: %.1f ms" % (t_enc * 1000))
print("Heads: %.1f ms" % (t_heads * 1000))
print("Total forward: %.1f ms" % (total * 1000))
