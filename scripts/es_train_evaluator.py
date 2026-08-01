#!/usr/bin/env python3
"""
(1+1)-ES hill-climbing for the neural evaluator weights.

Optimizes the 193-param evaluator (W1[16,10], B1[16], W2[16,1], B2[1])
in chris.py's v7 heuristic. Uses win-count + score-diff as combined
fitness (wins primary, score diff as tiebreaker).

This replaces the vanilla NES which suffered from:
- Noisy gradient estimates (193 params, 15 samples)
- Mean fitness not converging (flat around baseline)
- Good solutions lost between generations

(1+1)-ES is simpler: generate one perturbation, keep it if better.
With 1s1f-ES (1 parent, 1 offspring), we get reliable convergence.
With 1+1-ES (1 parent, 1 offspring, elitism), we never lose good solutions.

Usage:
    python scripts/es_train_evaluator.py [--generations 50] [--sigma 0.5]
"""

import argparse
import json
import os
import sys
import time

import numpy as np

# ── Paths ──
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "services", "worker", "engine", "nexus_wars"))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "test-bots", "personal_agent"))

import chris as chris_mod
from run_match import run_match, InProcessRunner
import benchmark_agents as ba


# ── Evaluator weight structure ──
TOTAL_PARAMS = 193  # 16*10 + 16 + 16 + 1


def get_evaluator_weights():
    """Extract current evaluator weights from chris module as a flat array."""
    w1 = np.array(chris_mod.W1, dtype=np.float64).flatten()
    b1 = np.array(chris_mod.B1, dtype=np.float64).flatten()
    w2 = np.array(chris_mod.W2, dtype=np.float64).flatten()
    b2 = np.array(chris_mod.B2, dtype=np.float64).flatten()
    return np.concatenate([w1, b1, w2, b2])


def set_evaluator_weights(flat):
    """Set evaluator weights in chris module from a flat array."""
    idx = 0
    w1_size = 16 * 10
    b1_size = 16
    w2_size = 16
    b2_size = 1

    w1 = flat[idx:idx + w1_size].reshape(16, 10).tolist()
    idx += w1_size
    b1 = flat[idx:idx + b1_size].tolist()
    idx += b1_size
    w2 = flat[idx:idx + w2_size].reshape(16, 1).tolist()
    idx += w2_size
    b2 = flat[idx:idx + b2_size].tolist()

    chris_mod.W1 = w1
    chris_mod.B1 = b1
    chris_mod.W2 = w2
    chris_mod.B2 = b2


def chris_agent(obs):
    try:
        return chris_mod.agent_fn(obs)
    except Exception:
        return []


def evaluate_individual(weights_flat, seeds, opponents):
    """Evaluate a single weight vector against all opponents.

    Returns combined fitness: win_count * 10000 + score_diff.
    Wins are primary signal; score_diff breaks ties.
    """
    set_evaluator_weights(weights_flat)
    wins = 0
    total_score_diff = 0.0
    total = 0
    for opp_name, opp_fn in opponents.items():
        for s in seeds:
            # Chris as player 0
            r = run_match([InProcessRunner(chris_agent), InProcessRunner(opp_fn)], seed=s)
            info = r.get("info", {})
            winner = info.get("winner", -1)
            scores = info.get("scores", [0, 0])
            total += 1
            if winner == 0:
                wins += 1
            total_score_diff += scores[0] - scores[1]
            # Chris as player 1
            r = run_match([InProcessRunner(opp_fn), InProcessRunner(chris_agent)], seed=s)
            info = r.get("info", {})
            winner = info.get("winner", -1)
            scores = info.get("scores", [0, 0])
            total += 1
            if winner == 1:
                wins += 1
            total_score_diff += scores[1] - scores[0]
    return float(wins) * 10000.0 + total_score_diff


def main():
    parser = argparse.ArgumentParser(description="(1+1)-ES hill-climbing for evaluator weights")
    parser.add_argument("--generations", type=int, default=50)
    parser.add_argument("--sigma", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.RandomState(args.seed)

    # Opponents
    opponents = {
        "fortress": ba.agent_fortress,
        "viper": ba.agent_viper,
        "chimera": ba.agent_chimera,
        "chimera-np": ba.agent_chimera_np,
    }

    # 4 seeds × 2 positions × 4 opponents = 32 matches per individual
    eval_seeds = [1000 + i * 7919 for i in range(4)]

    # Initialize from v7 weights
    mean = get_evaluator_weights()
    sigma = args.sigma
    best_fitness = evaluate_individual(mean, eval_seeds, opponents)
    best_weights = mean.copy()

    base_wins = int(best_fitness) // 10000
    base_score = best_fitness - base_wins * 10000.0
    print(f"(1+1)-ES training: {args.generations} generations, sigma={args.sigma}", flush=True)
    print(f"Total params: {TOTAL_PARAMS}", flush=True)
    print(f"Matches per individual: {len(opponents) * len(eval_seeds) * 2}", flush=True)
    print(f"Expected total time: ~{args.generations * len(opponents) * len(eval_seeds) * 2 * 0.7 / 60:.1f}min", flush=True)
    print(f"Baseline fitness: {best_fitness:.0f} (wins={base_wins}, score_diff={base_score:.0f})", flush=True)
    print(flush=True)

    start_time = time.time()
    no_improve_count = 0

    for gen in range(args.generations):
        gen_start = time.time()

        # 1s1f-ES: perturb, evaluate, keep if better
        perturbation = rng.randn(TOTAL_PARAMS)
        candidate = best_weights + sigma * perturbation
        candidate_fitness = evaluate_individual(candidate, eval_seeds, opponents)

        cand_wins = int(candidate_fitness) // 10000
        cand_score = candidate_fitness - cand_wins * 10000.0

        improved = candidate_fitness > best_fitness

        if improved:
            best_weights = candidate.copy()
            best_fitness = candidate_fitness
            # Increase sigma for more exploration after success
            sigma *= 1.2
            no_improve_count = 0
        else:
            no_improve_count += 1
            # Decrease sigma for more refinement after failure
            sigma *= 0.8
            sigma = max(0.02, sigma)

        gen_time = time.time() - gen_start
        elapsed = time.time() - start_time
        hrs_done = elapsed / 3600
        est_remaining = hrs_done / (gen + 1) * (args.generations - gen - 1) if gen > 0 else 0

        status = "✓ IMPROVED" if improved else "  "
        print(f"Gen {gen+1:3d}/{args.generations} | {status} | fitness={candidate_fitness:.0f} "
              f"(wins={cand_wins}, score={cand_score:.0f}) | best={best_fitness:.0f} "
              f"(wins={int(best_fitness)//10000}) | sigma={sigma:.4f} | "
              f"{gen_time:.1f}s | elapsed={elapsed:.0f}s | est_remaining={est_remaining:.1f}s",
              flush=True)

        # Checkpoint every 10 generations
        if (gen + 1) % 10 == 0:
            ckpt_path = os.path.join(REPO_ROOT, "test-bots", "personal_agent",
                                     f"_es_ckpt_gen{gen+1}.npz")
            np.savez(ckpt_path, weights=best_weights, fitness=np.array([best_fitness]),
                     sigma=np.array([sigma]))
            print(f"  Saved checkpoint: {ckpt_path}", flush=True)

    elapsed = time.time() - start_time
    print(f"\nFinal fitness: {best_fitness:.0f} (baseline: {base_wins * 10000 + base_score:.0f})", flush=True)
    print(f"Improvement: {best_fitness - base_fitness:+.0f}", flush=True)
    print(f"Win count: {int(best_fitness)//10000} (baseline: {base_wins})", flush=True)
    print(f"Total time: {elapsed:.0f}s", flush=True)

    # Save final weights
    out_path = os.path.join(REPO_ROOT, "test-bots", "personal_agent", "_es_weights.npz")
    np.savez(out_path, weights=best_weights, fitness=np.array([best_fitness]),
             sigma=np.array([sigma]))
    print(f"Saved weights: {out_path}", flush=True)

    # Save as evaluator weights for baking
    es_w1 = best_weights[:160].reshape(16, 10)
    es_b1 = best_weights[160:176]
    es_w2 = best_weights[176:192].reshape(16, 1)
    es_b2 = best_weights[192:193]

    b64_path = os.path.join(REPO_ROOT, "test-bots", "personal_agent", "_es_evaluator_b64.txt")
    with open(b64_path, 'w') as f:
        f.write(json.dumps({
            "W1": es_w1.tolist(),
            "B1": es_b1.tolist(),
            "W2": es_w2.tolist(),
            "B2": es_b2.tolist(),
        }))
    print(f"Saved evaluator weights: {b64_path}", flush=True)


if __name__ == "__main__":
    main()
