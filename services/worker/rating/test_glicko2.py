"""Quick sanity checks for the Glicko-2 module (no DB needed)."""
from rating.glicko2 import rate_match


def _main():
    # New teams at 600/350.
    a = (600.0, 350.0, 0.06)
    b = (600.0, 350.0, 0.06)

    # A beats B: A should rise, B should fall; first game moves fast.
    a2, b2 = rate_match(*a, 0.0, *b, 0.0, score_a=1.0)
    assert a2[0] > 600.0, a2
    assert b2[0] < 600.0, b2
    print(f"win:  A={a2[0]:.1f} ({a2[1]:.1f})  B={b2[0]:.1f} ({b2[1]:.1f})")

    # Symmetric: equal opponents, a draw leaves ratings ~unchanged.
    a3, b3 = rate_match(600.0, 60.0, 0.06, 0.0, 600.0, 60.0, 0.06, 0.0, 0.5)
    assert abs(a3[0] - 600.0) < 1.0, a3
    print(f"draw: A={a3[0]:.1f} B={b3[0]:.1f}")

    # RD clamp: a very strong/weak result cannot push RD below RD_MIN.
    a4, _ = rate_match(600.0, 30.0, 0.06, 0.0, 600.0, 350.0, 0.06, 365.0, 1.0)
    assert a4[1] >= 30.0 - 1e-6, a4
    print(f"clamp: A rd={a4[1]:.1f}")

    # Inactivity: RD grows when dt is large.
    a5, _ = rate_match(600.0, 60.0, 0.06, 365.0, 600.0, 60.0, 0.06, 0.0, 0.5)
    assert a5[1] > 60.0, a5
    print(f"decay: A rd {60.0:.1f} -> {a5[1]:.1f}")
    print("OK glicko2")


if __name__ == "__main__":
    _main()
