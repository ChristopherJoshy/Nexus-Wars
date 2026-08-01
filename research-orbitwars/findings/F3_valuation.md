# F3 — Scoring valuations & target selection

## Key claims

- **Net-ship surplus (melisgl winner):** value a planet by
  `ships - garrison_after_capture - projected_loss`. Core signal is surplus
  ships *after* a simulated capture, minus the cost to hold. Source:
  `player.lisp`.
- **Futures lookahead (melisgl):** project the board K turns for every
  candidate action, then take net ship delta (capture + growth differential).
  This is what makes Gauss strong in trade-down scenarios. Source:
  `player.lisp`.
- **kvatsa5 target valuation:** combine distance, production, current
  garrison, and turn-differential-to-flip. Greedy baseline = weakest neutral /
  weakest enemy planet. Source: kvatsa5 README.
- **kvatsa5 7 mission types:** rush / expand / defend / pillage / sniper /
  endgame / transit. Pick mission by phase + board state (behind vs ahead).
  Source: kvatsa5 README.
- **vkhydras reserve-walk (`compute_planet_reserve` / `reserve`):** assign
  *future ownership* per turn (not just current garrison). Value captures by
  net-growth over horizon; prioritize **guaranteed** captures; detect
  `doom` (about-to-be-lost) planets; plan `multi_prong` waves arriving in the
  same turn. Source: vkhydras #14 constants/logic.
- **finalize_chris `aim_at_target` + `coordinated_strikes`:** predict orbital
  positions, then group multiple fleets to arrive on the same turn
  (sniping). Energy gate skips launches when energy<20. Source:
  finalize_chris.py HEURISTIC_CODE.
- **Tie-for-win conservatism:** if ≥2 players tie for first place, switch to
  ultra-defensive posture (avoid risky trades that could let a third player
  steal the win). Source: kvatsa5 leaderboard bot note.
- **Reaction time (satirist):** launches need ~3-6 turn lead time to be
  meaningful; never commit a single delayed fleet without a follow-up.
  Source: satirist.org strategy guide.
