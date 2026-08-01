import sys, os, numpy as np
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "test-bots", "personal_agent"))
import chris as c

print("W1 shape:", np.array(c.W1).shape)
print("B1 shape:", np.array(c.B1).shape)
print("W2 shape:", np.array(c.W2).shape)
print("B2 shape:", np.array(c.B2).shape)

print("--- _forward_numpy with dummy ---")
try:
    r = c._forward_numpy([0.1]*10)
    print("numpy OK:", r)
except Exception as e:
    print("numpy FAILED:", type(e).__name__, e)

print("--- _forward_pure with dummy ---")
try:
    r = c._forward_pure([0.1]*10)
    print("pure OK:", r)
except Exception as e:
    print("pure FAILED:", type(e).__name__, e)

print("--- _neural_eval with dummy ---")
try:
    r = c._neural_eval([0.1]*10)
    print("neural_eval OK:", r)
except Exception as e:
    print("neural_eval FAILED:", type(e).__name__, e)
