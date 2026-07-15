# ABSOLOOP

**Bounded AI looping system** — auditable repair loops for `claude` and
`codex`, where a mission ends only when the builder reports it done with
evidence, an independent critic finds no blocking issue, and you approve.

> Private BLERBZ tooling. Blueprint: `ABSOLOOP_AI_LOOPER_SYSTEM.md` (kept
> outside this repo).

## How it works

```
objective ──► /goal contract ──► iterate: builder works, reports done? 
                                      │ (escalating thinking depth)
                                      ▼
                     done ──► integrity ► critic ► human gate
                                      ▼
                            delivery (git / local / out)
```

- **Evidence-gated** — a "done" claim counts only when it survives the
  independent critic's inspection of the working tree and your approval.
  Effort, narratives, and plausible diffs count for nothing.
- **Adversarial acceptance** — an independent read-only critic tries to
  disprove the result; weakened tests are an automatic rejection.
- **Bounded** — hard caps on iterations, wall clock, and dollars, with
  checkpointed state you can resume or extend at any time.
- **Engine-agnostic** — the same mission runs under the `claude` or `codex`
  CLI; the loop handles each engine's flags, budgets, and output shapes.

## Repo layout

```
bin/absoloop              startup CLI (pure Python, cross-platform)
bin/absoloop.cmd          Windows shim
templates/absoloop-run    reference loop runner copied into each project
templates/absoloop-init   POSIX bootstrap convenience copy
out/                      (gitignored) deliveries from `-d out` missions
```

This folder is the tooling home — mission projects are created wherever you
run the command.

## Setup

- **macOS / Linux**: symlink `bin/absoloop` into `~/.local/bin` (already done
  on the primary machine).
- **Windows**: copy this folder, add its `bin` to PATH; `absoloop` resolves to
  the `.cmd` shim.
- Requires Python 3, plus the `claude` and/or `codex` CLI for running loops.

## Usage

One shot — scaffold and start the loop, no prompts:

```
absoloop my-mission -o "Make all tests pass" -d local --start
```

Anything you omit is prompted for:

```
absoloop --help
absoloop              # fully interactive (asks name, confirms, then mission)
absoloop my-mission   # no confirmation; prompts for objective + delivery,
                        # then offers to start the loop immediately
absoloop .            # adopt the directory you are already in
```

It scaffolds `./<name>/` (scripts + `.absoloop/` config, git init) and
generates the mission's **/goal contract** at `.absoloop/goal.md`.
`--engine claude|codex` picks the engine and implies `--start`; without it,
interactive setup asks which engine to use in a multiple-choice prompt that
marks each one ✓ available or ✗ not found on PATH (non-interactive runs fall
back to the first engine found).

To start (or resume) the loop later from inside the project:

```
./scripts/absoloop-run --engine claude      # macOS/Linux
python scripts/absoloop-run --engine claude # Windows
```

Runner exit codes: `0` completed · `3` accepted, awaiting your approval ·
`2` stopped safely.

Mission lifecycle commands:

```
absoloop status                 # mission at a glance + exact next command
absoloop report                 # iteration-by-iteration results timeline
absoloop approve                # accept a mission stopped at the human gate
absoloop reject "use v2 API"    # answer the agent; lands in the next prompt
absoloop resume                 # re-enter the active mission's loop
absoloop resume --extend        # follow-on run: fresh budgets, prior work as context
```

## The /goal contract

Every mission gets a deterministic, programmatically generated goal definition
(`.absoloop/goal.md`) built from the objective: the objective is classified
(tests / bugfix / feature / refactor / perf / docs), which selects a tailored
definition of done, strategy ladder, **and thinking escalation ladder**. The
contract is embedded in every iteration prompt as ground truth for both
engines, and the generation is validated — an empty objective or a
malformed/de-escalating ladder is flagged (and a broken ladder is never
rendered into the contract).

Long-thinking loops are driven by the generated **thinking escalation ladder**
(`thinking_ladder` in `.absoloop/runtime.json` — the single source of truth
for both the contract and the runner), keyed to the repeated-failure count:

- **Claude** escalates the keyword `think → think hard → think harder →
  ultrathink` *and* the real extended-thinking budget — the runner exports the
  rung's `claude_thinking_tokens` as `MAX_THINKING_TOKENS` for that run.
- **Codex** escalates `model_reasoning_effort` (`minimal…xhigh` understood;
  never below what `runtime.json` configures).
- Each rung's `budget_scale` widens that iteration's per-run wall-clock and
  cost caps, so an ultrathink run isn't killed by limits sized for shallow ones.
- Mission types that reward deep analysis (bugfix, perf) start one rung up.

Hand-tune the ladder by editing `thinking_ladder` in `runtime.json` — a valid
edit survives re-adoption; changing the objective regenerates it. Inspect,
rebuild, or validate the contract:

```
absoloop goal           # print the mission's /goal contract
absoloop goal --regen   # regenerate it from .absoloop/runtime.json
absoloop goal --check   # validate objective/delivery/ladder; exit 1 on problems
```

## Delivery — where accepted work lands

Chosen at setup (`-d`, or the interactive prompt) and applied automatically
after acceptance (on `absoloop approve`, or on completion when the human gate
is disabled):

| mode | result |
|---|---|
| `git` | commits everything to a dedicated branch `absoloop/<loop_id>` |
| `local` | changes stay unstaged in the working tree (default) |
| `out` | changed files + report/goal/state/ledger exported to `~/absoloop/out/<loop_id>/` |

Re-run delivery any time with `python scripts/absoloop-run --deliver-only`.

## Results views

```
absoloop status   # budgets (with progress bars), delivery, latest artifacts
absoloop report   # agent runs with cost + summaries, done claims,
                  # critic verdicts, gates, delivery
```

The runner also writes `.absoloop/report.md` (markdown mission report) at every
stop, and includes it in `out` deliveries.

## Development notes

- `bin/absoloop` and `templates/absoloop-run` are pure standard-library Python
  (3.9+); no dependencies to install.
- The thinking ladder and goal contract share one generator in
  `bin/absoloop` (`build_thinking_ladder`, `generate_goal_markdown`,
  `validate_goal_config`); the runner only ever *consumes*
  `runtime.json.thinking_ladder`, falling back to its built-in default for
  projects scaffolded before ladders were per-mission.
- Existing projects pick up runner changes on re-adoption
  (`absoloop <path>` refreshes missing scripts) or by re-copying
  `templates/absoloop-run` over `scripts/absoloop-run`.
