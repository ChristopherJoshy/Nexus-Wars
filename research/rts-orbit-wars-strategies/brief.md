# Research Brief: Competitive RTS Space-Conquest Bot Strategies

**Date**: 2026-08-01
**Depth**: standard
**Question**: What are the winning strategies, heuristics, and architectures for 1v1 real-time space-conquest bots (Planet Wars / Orbit Wars / Nexus Wars style), suitable for direct implementation?

**Refined question**: Provide battle-tested, concrete, implementable techniques and heuristics (with numerical parameters and scoring functions) used by top-performing bots in Planet Wars competitions and Orbit Wars, covering (a) winning strategies from Google Code Jam / Kaggle Planet Wars; (b) key heuristics (threat detection, coordinated attacks, economy management, prediction); (c) hybrid neural+heuristic architectures; (d) specific techniques (orbital prediction, sun/body avoidance, multi-fleet coordination, endgame tactics); (e) how top bots handle being disadvantaged / comeback mechanics; (f) Orbit Wars specifically (Kaggle version, SimJeg/orbit-wars repo).

## Scope

IN:
- Planet Wars (Google Code Jam, Kaggle, Codingame, top-dev League) bot strategies
- Orbit Wars (Kaggle, SimJeg/orbit-wars) techniques and architecture
- Concrete heuristics with parameters and scoring formulas
- Neural+heuristic hybrid architectures proven in competition
- Comeback / disadvantage handling
- Endgame tactics for the 500-step cap games

OUT:
- Generic RTS (StarCraft) strategy (too broad / different mechanics)
- Pure theoretical / non-battle-tested proposals
- Hardware / optimization minutiae unrelated to game strategy

## Assumptions
- User is building an agent for a Planet Wars-style game with: planet production, fleets launched by angle+ship-count, straight-line travel, sum-of-ships combat, ~500 steps, variable fleet speed.
- User wants practical, copy-pasteable heuristics and parameters, not high-level prose.
- User has access to web search + web fetch (free sources only, no API keys).

## Angles
- A1: Planet Wars competition winners & their concrete strategies (Kaggle Planet Wars, Google Code Jam, Codingame, top-dev / League)
- A2: Key heuristics with parameters — threat detection, coordinated attacks, economy, prediction
- A3: Hybrid neural + heuristic architectures that succeeded in Planet Wars / Orbit Wars
- A4: Specific techniques — orbital prediction, body/sun avoidance, multi-fleet coordination, endgame tactics
- A5: Comeback mechanics / disadvantage handling in top bots
- A6: Orbit Wars specific (Kaggle Orbit Wars, SimJeg/orbit-wars repo, planet-transformer, int8 weights, 4x-rotation TTA, forward simulation)
