# DESIGN SKELETON — not built/run under the free constraint (needs the API brain). See deploy/README.md.
FROM python:3.11-slim

WORKDIR /app
COPY . /app
RUN pip install -e .

# The base image carries code + the SHARED baseline exemplars (identical for every customer).
# Each customer's TAILORED exemplars + config + secrets live on a per-customer volume mounted at
# /app/state (see docker-compose.yml) — so no customer's image contains another customer's data.

# Real deployment uses the API brain (the Max-plan CLI login can't containerize per-customer).
# The brain is already a built port (engine/core/brain.py: cli|api) — this is a flip, not a rewrite:
#   ENV ENGINE_BRAIN=api   ENGINE_BRAIN_MODEL=claude-sonnet-4-5   ANTHROPIC_API_KEY=<per-deployment key>
ENV ENGINE_BRAIN=api

# Illustrative — a per-customer service pinned to its own scope (see compose).
# ENTRYPOINT ["python", "-m", "engine.cli"]
