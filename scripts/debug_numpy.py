import numpy as np

W1 = [[float(i)]*10 for i in range(16)]
B1 = [0.5]*16
W2 = [[2.5] for _ in range(16)]
B2 = [1.0]

x = np.array([0.1]*10, dtype=np.float32)
w1 = np.array(W1, dtype=np.float32)
b1 = np.array(B1, dtype=np.float32)
w2 = np.array(W2, dtype=np.float32)
b2 = np.array(B2, dtype=np.float32)

print(f"x: {x.shape}")
print(f"W1: {w1.shape}, W1.T: {w1.T.shape}")
print(f"B1: {b1.shape}")
h = np.maximum(0.0, x @ w1.T + b1)
print(f"h: {h.shape}")
print(f"W2: {w2.shape}")
print(f"B2: {b2.shape}")
result = h @ w2 + b2
print(f"result: {result.shape}, value: {result}")
try:
    print(f"float(result): {float(result)}")
except TypeError as e:
    print(f"float(result) FAILED: {e}")
try:
    print(f"result.item(): {result.item()}")
except Exception as e:
    print(f"result.item() FAILED: {e}")
