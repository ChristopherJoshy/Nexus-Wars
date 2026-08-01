import numpy as np
import time

np.random.seed(42)
HIDDEN = 256
NUM_HEADS = 4
HEAD_DIM = 64
T = 20
N_BODIES = 40

def gelu(x):
    return x * 0.5 * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x * x * x)))

def layer_norm(x, weight, bias, eps=1e-5):
    x = x.astype(np.float32)
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) * np.sqrt(1.0 / (var + eps)) * weight + bias

# Generate test input
x_input = np.random.randn(1, 40, 20, 10).astype(np.float32)
body_mask = np.ones((1, 40), dtype=np.float32)

start = time.perf_counter()

# Planet embedding: conv blocks
batch_size, n_bodies, n_timesteps, input_dim = x_input.shape
valid = np.ones((batch_size, n_bodies, n_timesteps), dtype=np.float32)
valid = valid * body_mask[:, :, np.newaxis]
first_ts = x_input[:, :, 0, :] * valid[:, :, 0, np.newaxis]

y = x_input * valid[:, :, :, np.newaxis]
y = y.reshape(batch_size * n_bodies, n_timesteps, input_dim)
y_nct = y.transpose(0, 2, 1)  # (800, 10, 20) NCT
block_mask = valid.reshape(batch_size * n_bodies, n_timesteps)

# Conv block 0: 10->128 with residual conv
w0 = np.random.randn(128, 10, 5).astype(np.float32) * 0.1678
b0 = np.random.randn(128).astype(np.float32)
rw0 = np.random.randn(128, 10, 1).astype(np.float32)
rb0 = np.random.randn(128).astype(np.float32)
lnw0 = np.random.randn(128).astype(np.float32)
lnb0 = np.random.randn(128).astype(np.float32)

t0 = time.perf_counter()
# conv1d
padded = np.pad(y_nct, ((0,0),(0,0),(2,2)), mode='constant')
cols = np.lib.stride_tricks.sliding_window_view(padded, 5, axis=2)
cols = cols.transpose(1,3,0,2).reshape(50, 800*20)
conv_out = (w0.reshape(128, 50) @ cols).reshape(128, 800, 20).transpose(1,0,2) + b0[None, :, None]
# residual conv (kernel=1)
res_cols = np.lib.stride_tricks.sliding_window_view(y_nct, 1, axis=2)  # (800, 10, 20, 1)
res = (rw0.reshape(128, 10) @ res_cols.transpose(1,3,0,2).reshape(10, 800*20)).reshape(128, 800, 20).transpose(1,0,2) + rb0[None, :, None]
# gelu + residual
conv_out = gelu(conv_out) + res
conv_out = conv_out * block_mask[:, np.newaxis, :]
# layer norm (NCT -> NTC -> norm -> NCT)
conv_out = conv_out.transpose(0, 2, 1)
n = conv_out.shape[-1]
conv_out = (conv_out - conv_out.mean(axis=-1, keepdims=True)) / np.sqrt(conv_out.var(axis=-1, keepdims=True) + 1e-5) * lnw0 + lnb0
conv_out = conv_out.transpose(0, 2, 1)
t_conv0 = time.perf_counter() - t0

# Conv blocks 1-3: 128->128
t1 = time.perf_counter()
for i in range(3):
    w = np.random.randn(128, 128, 5).astype(np.float32) * 0.1678
    b = np.random.randn(128).astype(np.float32)
    lnw = np.random.randn(128).astype(np.float32)
    lnb = np.random.randn(128).astype(np.float32)
    padded = np.pad(conv_out, ((0,0),(0,0),(2,2)), mode='constant')
    cols = np.lib.stride_tricks.sliding_window_view(padded, 5, axis=2)
    cols = cols.transpose(1,3,0,2).reshape(640, 800*20)
    conv_out = (w.reshape(128, 640) @ cols).reshape(128, 800, 20).transpose(1,0,2) + b[None, :, None]
    conv_out = gelu(conv_out) + conv_out
    conv_out = conv_out * block_mask[:, np.newaxis, :]
    conv_out = conv_out.transpose(0, 2, 1)
    conv_out = (conv_out - conv_out.mean(axis=-1, keepdims=True)) / np.sqrt(conv_out.var(axis=-1, keepdims=True) + 1e-5) * lnw + lnb
    conv_out = conv_out.transpose(0, 2, 1)
t_conv = time.perf_counter() - t1

# Global avg pool + output projection
t2 = time.perf_counter()
emb_nct = conv_out.transpose(0, 2, 1).reshape(1, 40, 20, 128)  # (1, 40, 20, 128)
valid4 = valid[:, :, :, np.newaxis]
denom = np.maximum(valid4.sum(axis=2), 1.0)
emb = (emb_nct * valid4).sum(axis=2) / denom  # (1, 40, 128)
emb = np.concatenate([emb, first_ts], axis=-1)  # (1, 40, 138)
w_o = np.random.randn(256, 138).astype(np.float32)
b_o = np.random.randn(256).astype(np.float32)
embeddings = emb @ w_o.T + b_o  # (1, 40, 256)
t_pool = time.perf_counter() - t2

# Encoder
t3 = time.perf_counter()
enc_norm_w = np.random.randn(256).astype(np.float32)
hidden = (embeddings - embeddings.mean(axis=-1, keepdims=True)) / np.sqrt(embeddings.var(axis=-1, keepdims=True) + 1e-5) * enc_norm_w
hidden = hidden * body_mask[:, :, np.newaxis]

attn_mask = body_mask.astype(np.float32)
add_mask = np.where(attn_mask[:, None, None, :], 0.0, -1e9)
add_mask = add_mask[:, :, None, :]

final_norm_w = np.random.randn(256).astype(np.float32)
for i in range(7):
    ai = np.random.randn(256, 256).astype(np.float32)
    Wqkv = np.random.randn(768, 256).astype(np.float32)
    Wo_att = np.random.randn(256, 256).astype(np.float32)
    mlp_norm_w = np.random.randn(256).astype(np.float32)
    Wi = np.random.randn(768, 256).astype(np.float32)
    Wo_mlp = np.random.randn(256, 384).astype(np.float32)

    ai_input = hidden
    if i != 0:
        ai_input = (ai_input - ai_input.mean(axis=-1, keepdims=True)) / np.sqrt(ai_input.var(axis=-1, keepdims=True) + 1e-5) * ai

    qkv = ai_input @ Wqkv.T
    qkv = qkv.reshape(1, 40, 3, 4, 64)
    q = qkv[:, :, 0].transpose(0, 2, 1, 3)
    k = qkv[:, :, 1].transpose(0, 2, 1, 3)
    v = qkv[:, :, 2].transpose(0, 2, 1, 3)
    scores = q @ k.transpose(0, 1, 3, 2) * (1.0 / np.sqrt(64))
    scores = scores + add_mask
    attn = np.exp(scores - scores.max(axis=-1, keepdims=True))
    attn = attn / attn.sum(axis=-1, keepdims=True)
    ao = (attn @ v).transpose(0, 2, 1, 3).reshape(1, 40, 256)
    attn_out = ao @ Wo_att.T
    hidden = hidden + attn_out

    mlp_in = (hidden - hidden.mean(axis=-1, keepdims=True)) / np.sqrt(hidden.var(axis=-1, keepdims=True) + 1e-5) * mlp_norm_w
    wi_out = mlp_in @ Wi.T
    inp = wi_out[..., :384]
    gate = wi_out[..., 384:]
    mlp_out = gelu(inp) * gate @ Wo_mlp.T
    hidden = hidden + mlp_out

hidden = (hidden - hidden.mean(axis=-1, keepdims=True)) / np.sqrt(hidden.var(axis=-1, keepdims=True) + 1e-5) * final_norm_w
t_enc = time.perf_counter() - t3

# Heads
t4 = time.perf_counter()
launch_w = np.random.randn(1, 256).astype(np.float32)
launch_b = np.random.randn(1).astype(np.float32)
launch_logits = (hidden @ launch_w.T + launch_b).squeeze(-1)  # (1, 40)
launch_prob = 1.0 / (1.0 + np.exp(-launch_logits))

q = hidden @ np.random.randn(256, 256).astype(np.float32).T
k = hidden @ np.random.randn(256, 256).astype(np.float32).T
q = q.reshape(1, 40, 4, 64).transpose(0, 2, 1, 3)
k = k.reshape(1, 40, 4, 64).transpose(0, 2, 1, 3)
scores = q @ k.transpose(0, 1, 3, 2) / np.sqrt(64)
hw = np.exp(np.random.randn(4).astype(np.float32))
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
