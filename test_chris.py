import os
import sys

# Add engine to path
sys.path.append(os.path.join("services", "worker", "engine"))

from nexus_wars.run_match import run_match, InProcessRunner

# Run a match between chrisv99.py and AEGIS bot
results = run_match(
    seed=42,
    agent_paths=[
        os.path.join("test-bots", "personal_agent", "chrisv99.py"),
        os.path.join("extracted_agents", "Rank1_AEGIS_Bot1_aethon.py")
    ],
    runner_cls=InProcessRunner
)

print(results)
