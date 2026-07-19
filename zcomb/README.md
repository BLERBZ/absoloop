# ZComb — optional Absoloop Kanban UI

Optional live view for Absoloop’s **Synergetic Loops** — vendored
[ZCombinator](https://github.com/BLERBZ/zcomb) monitoring dashboard, wired in
as a browser Kanban / activity UI.

## What you get

- Agent cards for the builder, critic, and spawned teammates
- Kanban columns driven by Absoloop mission phase
- Live activity feed bridged from `.absoloop/tmp/live.jsonl`
- Metrics (iteration, spend, heartbeat) from `monitor.json`

Absoloop owns the bridge (`absoloop_harness/zcomb.py`). The React app under
`monitor/` stays a thin viewer over ZComb state files.

## Start from Absoloop

```bash
absoloop --zcomb                     # same briefing/launch as absoloop + Kanban
absoloop "Make tests pass" --zcomb   # objective + launch with Kanban
absoloop zcomb -C ./my-mission       # dashboard only (monitor a running mission)
absoloop zcomb --port 3141 --no-browser
```

Requires **Node.js 18+**. On first run Absoloop installs `monitor/` deps and
builds the React app, then bridges telemetry into `.absoloop/zcomb/state/`.

Dashboard default: [http://localhost:3141](http://localhost:3141)

## How the bridge works

```text
.absoloop/tmp/monitor.json  ─┐
.absoloop/tmp/live.jsonl    ─┼─► absoloop_harness/zcomb.py ─► .absoloop/zcomb/state/
.absoloop/state.json        ─┘         │
                                       ▼
                              zcomb/monitor (Express + React)
                              http://localhost:3141
```

The bridge maps Absoloop phases to Kanban columns, synthesizes teammate cards
from spawn evidence in the activity feed, and keeps heartbeats fresh while the
mission is live. Stopping the Absoloop process (or `absoloop abort`) lets the
dashboard go stale naturally.

## Layout

```text
zcomb/
  monitor/           Express API + React dashboard
  setup.sh           Upstream-style local setup
  zcomb.sh           Upstream-style launcher
  ZCombinator-Flow.md
  examples/
```

Prefer `absoloop zcomb` / `absoloop --zcomb` over calling `zcomb.sh` directly
when you are inside an Absoloop mission — the CLI owns PATH, port, and the
telemetry bridge.

## License

Upstream license: MIT (see `LICENSE`). Original project:
https://github.com/BLERBZ/zcomb

Mission-loop context: [docs/mission-loop.md](../docs/mission-loop.md).
