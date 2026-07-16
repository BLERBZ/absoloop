# Absoloop multi-provider harness — user guide

The harness runs **Grok Build, Claude Code, and Codex** as first-class
backends behind one Absoloop UX. Each provider keeps its native
authentication, tools, sessions, permissions, and sandboxing; Absoloop owns
worktree isolation, event normalization, deterministic quality gates, and
run artifacts. Design details: `docs/architecture/multi-provider-harness.md`.

## Setup

Nothing to install beyond the provider CLIs you want to use:

- `grok` — `curl -fsSL https://x.ai/cli/install.sh | bash`, then `grok login`
- `claude` — Claude Code CLI, logged in
- `codex` — Codex CLI, logged in

Check readiness (path, version, auth hint, capabilities, actionable fixes):

```bash
absoloop doctor
absoloop providers        # capability matrix
```

## Running tasks

```bash
absoloop run "Fix the failing tests"              # briefing → pick provider → Enter
absoloop run --provider grok   "Fix the failing tests" -y   # skip briefing
absoloop run --provider claude "Refactor the auth module"
absoloop run --provider codex  "Add the requested feature"

absoloop build --strategy race    --providers grok,claude,codex "Implement issue #123"
absoloop build --strategy council --providers grok,claude,codex "Implement issue #123"
absoloop review --implementer claude --reviewer codex "Harden this change"
```

Every run executes in an **isolated git worktree** (never your working
tree), streams provider activity as normalized events, runs the configured
deterministic gates, and exports a patch. Nothing touches your tree until:

```bash
absoloop inspect                  # list harness runs (LIVE badge when running)
absoloop inspect <run-id>         # manifest, candidates, gate results, live PIDs
absoloop cancel <run-id>          # kill a live run from another terminal
absoloop apply <run-id>           # apply the selected candidate's patch
absoloop apply <run-id> --candidate codex
absoloop resume <run-id> "also update the changelog"   # continue the native session
```

Flags: `--profile read|edit|full` (permission profile, default from config),
`--keep-worktrees` (retain candidate trees for debugging), `--verbose`
(stream text/progress lines), `--no-isolate` (run `single` directly in the
repo root — single-provider only).

### Cancelling a live run

While a harness run is in progress it writes `.absoloop/runs/<run-id>/live.json`
(orchestrator PID + each provider child pid/pgid) and watches for
`cancel.requested`. From a second terminal:

```bash
absoloop cancel <run-id>
```

That writes the cancel flag, SIGTERM/SIGKILL's every recorded process group,
signals the orchestrator, and finalizes the run record as `status: cancelled`
so `inspect` stays accurate even if the original process dies mid-write.

## Strategies

| strategy | what happens |
|---|---|
| `single` | one provider, one worktree, gates, patch |
| `review` | implementer works; a different provider reviews read-only; implementer fixes findings via session resume; gates re-run |
| `race` | all providers implement independently in isolated worktrees; gates rank candidates; winner re-verified in an integration worktree |
| `council` | planner writes plan + acceptance criteria → parallel implementers → reviewer verifies the leader → integrator applies and re-runs all gates |

Selection is deterministic: gate survivors first, then fewest gate failures,
then completed runs, then smallest diff. LLM judgment is never applied
before deterministic gates.

## Configuration

Copy `absoloop.toml.example` to your project as `absoloop.toml` (or to
`~/.absoloop/absoloop.toml` for user scope). Precedence is
CLI > project > user > defaults, and

```bash
absoloop config
```

prints every resolved value with its source.

## Security model

- Provider CLIs are spawned as argv arrays — no shell, so hostile prompt or
  path text is inert.
- Child processes get a minimal allowlisted environment; Absoloop never
  copies or persists provider credential files.
- Secrets (token-shaped literals and secret-named env values) are redacted
  from events, logs, and manifests.
- Permission profiles map to the safest provider-native settings and fail
  closed when no safe mapping exists.
- Cancellation (Ctrl+C, or `absoloop cancel <run-id>` from another terminal)
  kills the provider's whole process group and still writes a valid run
  record (`status: cancelled` in the manifest + live.json).

## Run artifacts

```text
.absoloop/runs/<run-id>/
  manifest.json      provider versions, capabilities, session ids, prompt hash,
                     permission profile, gate outcomes, usage/cost, diff hashes
  events.jsonl       normalized, redacted event stream
  plan.md            council plan (when applicable)
  summary.md         human-readable run report
  candidates/<role>/ final.json · diff.patch · test.log · stderr.log
```

## Migration notes

- The legacy mission loop (`absoloop <name>`, `status`, `watch`, `report`,
  `goal`, `approve`, `reject`) is unchanged and remains the default flow;
  it is covered by characterization tests (`tests/test_characterization_*`).
- `absoloop resume` now checks harness run ids first
  (`.absoloop/runs/<id>`); anything else falls through to the legacy
  mission resume, so existing missions behave exactly as before.
- New harness subcommands (`doctor`, `providers`, `run`, `build`, `review`,
  `inspect`, `apply`, `config`) are reserved words — a legacy mission
  project can no longer be named exactly one of these.
- Legacy `.absoloop/runtime.json`, `state.json`, etc. are untouched; the
  harness only adds `.absoloop/runs/` and `.absoloop/worktrees/`
  (the latter is transient and cleaned after each run).

## Platforms

Absoloop targets **Linux, macOS, and Windows**:

| Concern | Behavior |
|---|---|
| Install | `bin/absoloop` auto-detects `ABSOLOOP_HOME`; Windows `absoloop.cmd` sets it |
| Providers | `shutil.which` + PATHEXT — argv always uses a resolved path |
| Cancel | Unix process groups · Windows `taskkill /T` process trees |
| Gates | `python` / `python3` rewritten to the Absoloop interpreter |
| Codex Micro | `absoloop do <action>` on all OS; TTY listen is Unix (`termios`) |
| Report viewer | `open` / `xdg-open` / `os.startfile` |

Run `absoloop doctor` after install — it prints environment, auth hints for
Grok / Claude / Codex, gate command, and Micro setup tips.

## Testing

```bash
python -m unittest discover -s tests             # offline, no credentials
ABSOLOOP_LIVE_SMOKE=1 ABSOLOOP_SMOKE_CLAUDE=1 \
  python -m unittest tests.test_harness_workflows.LiveSmoke   # opt-in live smoke
```

Fake-provider executables under `tests/fakes/` simulate all three stream
formats plus failure modes (partial JSON, unknown events, stderr noise,
non-zero exit, hang for timeout/cancel), so the whole pipeline is testable
offline.
