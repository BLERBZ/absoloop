# Schedules — cron / interval mission triggers

Absoloop schedules fire `resume`, `extend`, or `start` actions on a
calendar without weakening the integrity → critic → **human gate**.
Schedules **never** auto-approve — if the mission is awaiting your decision,
the tick skips until you `approve` or `reject`.

## Why

Long missions (week-long game pipelines, nightly verification) need
bounded segments with human breaks. Schedules chain those segments:

1. A Friday `extend` starts the next weekly objective with fresh budgets
2. Weekday `resume` ticks continue work between operator breaks
3. If the mission is `AWAITING_APPROVAL`, the tick **skips** until you
   `absoloop approve` or `absoloop reject`

## Quick start

```bash
cd /path/to/project   # must already be an Absoloop mission

absoloop schedule add --id friday-rotate \
  --cron "0 0 * * 5" --tz America/New_York \
  --action extend \
  -m "Plan, design, and ship the next unique weekly deliverable" \
  --hours 24 --iterations 50 --budget 150 \
  --require-status COMPLETED,BUDGET_EXHAUSTED

absoloop schedule add --id weekday-segment \
  --every 24h --action resume

absoloop schedule list
absoloop schedule tick --dry-run
absoloop schedule tick --once
```

Host cron alternative (no daemon):

```cron
* * * * * cd /path/to/project && absoloop schedule tick --once
```

Or run the built-in daemon:

```bash
absoloop schedule daemon start          # background
absoloop schedule daemon status
absoloop schedule daemon stop
# foreground (useful while developing):
absoloop schedule daemon start -f --interval 60
```

## CLI

| Command | Purpose |
|---|---|
| `schedule add` | Create/replace `.absoloop/schedules/<id>.toml` |
| `schedule list` / `show` | Inspect |
| `schedule enable` / `disable` / `rm` | Lifecycle |
| `schedule tick [--dry-run]` | Fire due jobs (what cron/daemon call) |
| `schedule history [id]` | Audit trail |
| `schedule daemon start\|stop\|status` | Long-lived poller |

### `add` flags

- `--cron "M H DOM MON DOW"` — 5-field cron (stdlib parser; `0`/`7` = Sunday)
- `--every 6h` — interval (`Xm` / `Xh` / `Xd`, min 60s)
- `--tz America/New_York` — IANA zone for cron matching
- `--action resume\|extend\|start`
- `-m` / `--note` — extend focus (becomes a DoD item)
- `--hours` `--iterations` `--budget` `--min-iterations` — extend budgets
- `--if-busy skip\|queue` — default `skip` when a loop/harness is live
- `--require-status A,B` — only fire when `state.json` status matches

## On-disk layout

```text
.absoloop/schedules/
  <id>.toml           # definition
  state.json          # last_fire_at / next_fire_at per id
  history.jsonl       # append-only audit

~/.absoloop/schedules/
  index.json          # projects the daemon should tick
  daemon.json         # daemon pid + heartbeat
```

## Safety

- **No auto-approve** — `AWAITING_APPROVAL` → skip (exit 3 recorded in history)
- **Busy detection** — live `.absoloop/tmp/monitor.json` or harness `live.json`
- **Human breaks** — `schedule disable <id>` or `daemon stop`, then continue later
- Schedules call the same `absoloop resume` / `absoloop extend` paths as a human

## Example: week-long mission with breaks

```bash
# Segment 1 — kick off
absoloop . -o "Ship the weekly feature" -d local

# After a break / budget stop:
absoloop resume

# Or let the weekday schedule resume for you:
absoloop schedule add --id day-chunk --every 24h --action resume
absoloop schedule daemon start
```
