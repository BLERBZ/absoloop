# ZCombinator (vendored as Absoloop ZComb UI)

Open-source multi-agent monitoring dashboard. Inside Absoloop, prefer
``absoloop zcomb`` / ``absoloop --zcomb`` — those wire the telemetry bridge
in ``absoloop_harness/zcomb.py``. See [README.md](README.md).

## Project structure

- **monitor/** — Express API + React dashboard (agent cards, Kanban, activity)
- **setup.sh** — Upstream-style local dependency install
- **zcomb.sh** — Upstream-style launcher (Absoloop CLI is preferred in-mission)
- **ZCombinator-Flow.md** — Original multi-agent workflow prompt template
- **examples/** — Sample objectives / demo material
