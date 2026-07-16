# ZComb — optional Absoloop UI

Vendored [ZCombinator](https://github.com/BLERBZ/zcomb) monitoring dashboard,
wired into Absoloop as an optional Kanban / live UI.

## Start from Absoloop

```bash
absoloop --zcomb                 # dashboard for the current project
absoloop zcomb -C ./my-mission   # same, explicit project
absoloop "Make tests pass" --zcomb   # brief + launch, open ZComb alongside
```

Requires **Node.js 18+**. On first run Absoloop installs `monitor/` deps and
builds the React app, then bridges `.absoloop/tmp/monitor.json` + `live.jsonl`
into ZComb state files under `.absoloop/zcomb/state/`.

Dashboard default: [http://localhost:3141](http://localhost:3141)

Upstream license: MIT (see `LICENSE`). Original project: https://github.com/BLERBZ/zcomb
