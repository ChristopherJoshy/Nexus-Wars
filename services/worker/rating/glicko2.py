"""
Glicko-2 rating with Lichess-style fractional rating periods.

Updates happen immediately after each match (not in batched periods). RD
decays with inactivity so stale ratings lose confidence. Constants follow the
Lichess tuning referenced in the design doc.

Usage:
    new_a, new_b = rate_match(ra, rda, vola, dt_a, rb, rdb, volb, dt_b, score_a)
    # score_a in {1 (A wins), 0 (A loses), 0.5 (draw)}
"""
import math

TAU = 0.5
RD_MIN = 30.0
RD_MAX = 350.0
VOL_DEFAULT = 0.06
VOL_MIN = 0.01
VOL_MAX = 0.5
SCALE = 173.7178
RATING_BASE = 600.0
PERIODS_PER_DAY = 0.21436  # RD grows 60 -> 110 over one year of inactivity


def _to_internal(rating, rd):
    return (rating - RATING_BASE) / SCALE, rd / SCALE


def _from_internal(mu, phi):
    return mu * SCALE + RATING_BASE, phi * SCALE


def _g(phi):
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _E(mu, mu_j, phi_j):
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _step5(vol, phi_star, delta, tau=TAU):
    """Iterate to find the new volatility (Glickman step 5)."""
    a = math.log(max(vol * vol, 1e-300))
    eps = 1e-6
    A = a

    def f(x):
        ex = math.exp(x)
        return (ex * (delta * delta - phi_star * phi_star - ex) /
                (2.0 * (phi_star * phi_star + ex) ** 2)) - \
               (x - a) / (tau * tau)

    diff = delta * delta - phi_star * phi_star
    if diff > 0:
        B = math.log(diff)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        B = a - k * tau

    fa, fb = f(A), f(B)
    # Bisection
    for _ in range(100):
        C = (A + B) / 2.0
        fc = f(C)
        if abs(fc) < eps or (B - A) / 2.0 < eps:
            return math.exp(C)
        if fc * fa < 0:
            B, fb = C, fc
        else:
            A, fa = C, fc
    return math.exp((A + B) / 2.0)


def _rate_one(rating, rd, vol, days_since, opp_rating, opp_rd, score):
    mu, phi = _to_internal(rating, rd)
    mu_j, phi_j = _to_internal(opp_rating, opp_rd)

    t = max(0.0, days_since) * PERIODS_PER_DAY
    phi_star = math.sqrt(phi * phi + t * vol * vol)

    gj = _g(phi_j)
    e = _E(mu, mu_j, phi_j)
    v = 1.0 / (gj * gj * e * (1.0 - e))
    delta = v * gj * (score - e)

    vol_new = max(VOL_MIN, min(VOL_MAX, _step5(vol, phi_star, delta)))
    phi_prime = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_prime = mu + phi_prime * phi_prime * gj * (score - e)

    r_new, rd_new = _from_internal(mu_prime, phi_prime)
    rd_new = min(RD_MAX, max(RD_MIN, rd_new))
    r_new = max(0.0, r_new)
    return r_new, rd_new, vol_new


def rate_match(ra, rda, vola, dt_a, rb, rdb, volb, dt_b, score_a):
    """Return updated (rating_a, rd_a, vol_a), (rating_b, rd_b, vol_b)."""
    score_b = 1.0 - score_a  # 1->0, 0->1, 0.5->0.5
    a = _rate_one(ra, rda, vola, dt_a, rb, rdb, score_a)
    b = _rate_one(rb, rdb, volb, dt_b, ra, rda, score_b)
    return a, b
