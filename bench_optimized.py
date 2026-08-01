import numpy as np
import time

np.random.seed(42)

def gelu(x):
    return x * 0.5 * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x * x * x)))

def layer_norm(x, weight, bias, eps=1e-5):
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) * np.reciprocal(np.sqrt(var + eps)) * weight + bias

def conv1d_im2col(x_nct, weight, bias, padding):
    """Faster conv1d using im2col + single matmul."""
    N, Cin, Tlen = x_nct.shape
    Cout, _, K = weight.shape
    padded = np.pad(x_nct, ((0,0),(0,0),(padding,padding)), constant_values=0)
    # im2col: (N, Cin, Tlen, K) -> (Cin*K, N*Tlen)
    cols = np.lib.stride_tricks.sliding_window_view(padded, K, axis=2)
    cols = cols.transpose(1, 3, 0, 2).reshape(Cin * K, N * Tlen)
    w = weight.reshape(Cout, Cin * K)
    out = (w @ cols).reshape(Cout, N, Tlen).transpose(1, 0, 2)
    return out + bias[np.newaxis, :, np.newaxis]

# Test with actual conv dimensions
N, Cin, Tlen = 40, 128, 20
Cout, K = 128, 5
x = np.random.randn(N, Cin, Tlen).astype(np.float32)
w = np.random.randn(Cout, Cin, K).astype(np.float32) * 0.1678
b = np.random.randn(Cout).astype(np.float32)

# Benchmark im2col approach
start = time.perf_counter()
for _ in range(4):
    out = conv1d_im2col(x, w, b, 2)
elapsed = time.perf_counter() - start
print("4x conv1d (128->128) im2col: %.1f ms" % (elapsed * 1000))

# Benchmark kernel loop approach
def conv1d_loop(x_nct, weight, bias, padding):
    N, Cin, Tlen = x_nct.shape
    Cout, _, K = weight.shape
    padded = np.pad(x_nct, ((0,0),(0,0),(padding,padding)), constant_values=0)
    out = np.zeros((N, Cout, Tlen), dtype=np.float32)
    for k in range(K):
        inp = padded[:, :, k:k+Tlen]
        out += np.matmul(weight[:, :, k], inp.transpose(1, 0, 2).reshape(Cin, N * Tlen)).reshape(Cout, N, Tlen).transpose(1, 0, 2)
    return out + bias[np.newaxis, :, np.newaxis]

x = np.random.randn(40, 128, 20).astype(np.float32)
start = time.perf_counter()
for _ in range(4):
    out = conv1d_loop(x, w, b, 2)
elapsed = time.perf_counter() - start
print("4x conv1d (128->128) loop: %.1f ms" % (elapsed * 1000))

# Full model benchmark with im2col conv
def gelu(x):
    return x * 0.5 * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x * x * x)))

def layer_norm(x, weight, bias, eps=1e-5):
    mean = x.mean(axis=-1, keepdims=True)
    var = x.var(axis=-1, keepdims=True)
    return (x - mean) * np.reciprocal(np.sqrt(var + eps)) * weight + bias

x_input = np.random.randn(1, 40, 20, 10).astype(np.float32)
body_mask = np.ones((1, 40), dtype=np.float32)

start = time.perf_counter()
batch_size, n_bodies, n_timesteps, input_dim = 1, 40, 20, 10
y = x_input.reshape(batch_size * n_bodies, n_timesteps, input_dim).astype(np.float32)
y_nct = y.transpose(0, 2, 1)  # (40, 10, 20) NCT
block_mask = body_mask[0][:, np.newaxis, np.newaxis]  # (40, 1, 1)

# Conv block 0
w0 = np.random.randn(128, 10, 5).astype(np.float32) * 0.1678
b0 = np.random.randn(128).astype(np.float32)
rw0 = np.random.randn(128, 10, 1).astype(np.float32)
rb0 = np.random.randn(128).astype(np.float32)
lnw0 = np.ones(128, dtype=np.float32)
lnb0 = np.zeros(128, dtype=np.float32)

c = conv1d_im2col(y_nct, w0, b0, 2)
r = conv1d_im2col(y_nct, rw0, rb0, 0)
c = gelu(c + r) * block_mask
c_tc = c.transpose(0, 2, 1)
c_tc = layer_norm(c_tc, lnw0, lnb0)
c = c_tc.transpose(0, 2, 1)

# Conv blocks 1-3
for i in range(3):
    w = np.random.randn(128, 128, 5).astype(np.float32) * 0.1678
    b = np.random.randn(128).astype(np.float32)
    lnw = np.ones(128, dtype=np.float32)
    lnb = np.zeros(128, dtype=np.float32)
    prev = c
    c = conv1d_im2col(c, w, b, 2)
    c = gelu(c + prev) * block_mask
    c_tc = c.transpose(0, 2, 1)
    c_tc = layer_norm(c_tc, lnw, lnb)
    c = c_tc.transpose(0, 2, 1)

# Pool + embed
emb = c.transpose(0, 2, 1).reshape(1, 40, 20, 128)
emb = (emb * body_mask[:, :, np.newaxis, np.newaxis]).sum(axis=2) / 20.0
first_ts = x_input[:, :, 0, :]
emb = np.concatenate([emb, first_ts], axis=-1)
w_o = np.random.randn(256, 138).astype(np.float32)
b_o = np.random.randn(256).astype(np.float32)
embeddings = emb @ w_o.T + b_o

# Encoder
enc_norm_w = np.ones(256, dtype=np.float32)
hidden = layer_norm(embeddings, enc_norm_w, np.zeros(256, dtype=np.float32)) * body_mask[:, :, np.newaxis]
add_mask = np.where(body_mask[:, np.newaxis, np.newaxis, :] > 0, 0.0, -1e9)

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

    mlp_in = layer_norm(hidden, mlp_norm_w, np.zeros(256, dtype=np.float32))
    wi_out = mlp_in @ Wi.T
    inp = wi_out[..., :384]
    gate = wi_out[..., 384:]
    mlp_out = gelu(inp) * gate @ Wo_mlp.T
    hidden = hidden + mlp_out

hidden = layer_norm(hidden, np.ones(256, dtype=np.float32), np.zeros(256, dtype=np.float32))
hidden = hidden * body_mask[:, :, np.newaxis]

# Heads
launch_w = np.random.randn(1, 256).astype(np.float32)
launch_b = np.zeros(1, dtype=np.float32)
tgt_q = np.random.randn(256, 256).astype(np.float32)
tgt_k = np.random.randn(256, 256).astype(np.float32)
tgt_hw = np.random.randn(4).astype(np.float32)

launch_logits = (hidden @ launch_w.T + launch_b).squeeze(-1)
launch_prob = 1.0 / (1.0 + np.exp(-launch_logits))
q = hidden @ tgt_q.T
k = hidden @ tgt_k.T
q = q.reshape(1, 40, 4, 64).transpose(0, 2, 1, 3)
k = k.reshape(1, 40, 4, 64).transpose(0, 2, 1, 3)
scores = q @ k.transpose(0, 1, 3, 2) / np.sqrt(64)
hw = np.exp(tgt_hw)
hw = hw / hw.sum()
target_logits = np.sum(scores * hw[np.newaxis, :, np.newaxis, np.newaxis], axis=1)

total = time.perf_counter() - start
print("Total forward (im2col conv): %.1f ms" % (total * 1000))
