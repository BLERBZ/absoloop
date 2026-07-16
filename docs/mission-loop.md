# Mission loop — deep dive

Companion to the [README](../README.md). This is the long-form contract for
how an Absoloop mission runs end-to-end.

## Flow

```text
objective ──► /goal contract ──► iterate: builder works, reports done?
                                      │ (escalating thinking depth)
                                      ▼
                     done ──► integrity ► critic ► human gate
                                      ▼
                            delivery (git / local / out)
```

- **Evidence-gated** — a “done” claim counts only when it survives the
  independent critic’s inspection of the working tree and your approval.
- **Adversarial acceptance** — the critic tries to disprove the result;
  weakened tests are an automatic rejection.
- **Bounded** — hard caps on iterations, wall clock, and dollars, with
  checkpointed state you can resume or extend.
- **Engine-agnostic** — the same mission runs under `claude` or `codex`
  (and harness providers for one-shot / race / council flows).
- **Observable** — console stream + `.absoloop/tmp/monitor.json` +
  `live.jsonl`, rendered by `absoloop watch`.

## Mission Briefing

```bash
absoloop "Make all tests pass"     # objective-first; review; Enter launches
absoloop                           # prompt for objective, then review
absoloop . -o "Fix the crash"      # adopt cwd with the same briefing
absoloop my-mission -o "…" -y      # skip review, lock in and launch
absoloop "…" --no-start            # scaffold only
```

Keys: `Enter` launch · `o` objective · `e` engine · `d` delivery ·
`n` rename · `g` preview `/goal` · `q` abort.

Scaffold writes scripts + `.absoloop/` config, initializes git when needed,
and generates the `/goal` contract at `.absoloop/goal.md`.

```bash
./scripts/absoloop-run --engine claude      # macOS/Linux
python scripts/absoloop-run --engine claude # Windows
```

Exit codes: `0` completed · `3` awaiting approval · `2` stopped safely.

## Lifecycle commands

```bash
absoloop status
absoloop watch
absoloop report              # Markdown + lite HTML viewer
absoloop approve
absoloop reject "guidance"
absoloop resume
absoloop resume --extend
absoloop schedule …          # cron / interval triggers (see docs/schedule.md)
```

## The `/goal` contract

Generated from the objective classification (tests / bugfix / feature /
refactor / perf / docs). Embedded in every iteration prompt.

Long-thinking loops use `thinking_ladder` in `.absoloop/runtime.json`:

- **Claude** escalates `think → think hard → think harder → ultrathink` and
  exports `MAX_THINKING_TOKENS` from the rung’s `claude_thinking_tokens`.
- **Codex** escalates `model_reasoning_effort` (never below configured floor).
- Each rung’s `budget_scale` widens per-run wall-clock and cost caps.
- Bugfix / perf missions start one rung up.

```bash
absoloop goal
absoloop goal --regen
absoloop goal --check
```

## Skills — loopers-toolbox

Installed into `.claude/skills/` and `.codex/skills/` from
`templates/skills/` per `toolbox.json`:

| skill | engines | upstream |
|---|---|---|
| `skill-creator` | both | [anthropics/skills](https://github.com/anthropics/skills) |
| `ai-ready` | both | [johnpapa/ai-ready](https://github.com/johnpapa/ai-ready) |
| `tdd` | both | [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) |
| `agent-browser` | both | [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) |
| `mcp-builder` | both | [anthropics/skills](https://github.com/anthropics/skills) |
| `frontend-design` | both | [anthropics/skills](https://github.com/anthropics/skills) |
| `claude-api` | claude | [anthropics/skills](https://github.com/anthropics/skills) |
| `cli-creator` | codex | [openai/skills](https://github.com/openai/skills) |

Skills are authorized infrastructure in the `/goal` contract; the critic
audits them like any artifact. They persist across `resume --extend`.

## Delivery

| mode | result |
|---|---|
| `git` | commit to `absoloop/<loop_id>` |
| `local` | leave working tree unstaged |
| `out` | export to `~/absoloop/out/<loop_id>/` |

Re-run with `python scripts/absoloop-run --deliver-only`.

## Monitoring & reports

While running, every tool call / command / message streams to the console
(respects `NO_COLOR`) and into:

- `monitor.json` — phase, iteration, spend, thinking, pid + heartbeat
- `live.jsonl` — append-only activity feed

```bash
absoloop watch --once
absoloop report --terminal
```

Full agent event streams persist as
`iteration-NNNN-agent-result.stream.jsonl` / `.events.jsonl`.
`absoloop report` regenerates `.absoloop/report.md` and opens
`.absoloop/report.html`.

## Development notes

- Thinking ladder + goal contract generators live in `bin/absoloop`
  (`build_thinking_ladder`, `generate_goal_markdown`, `validate_goal_config`).
- The runner only *consumes* `runtime.json.thinking_ladder`.
- Re-adoption (`absoloop <path>`) refreshes missing scripts; or re-copy
  `templates/absoloop-run` over `scripts/absoloop-run`.
