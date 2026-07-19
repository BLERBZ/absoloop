# Getting started

**AbsoLoop** is *Synergetic Loops* — builder, critic, human, and local agent
CLIs compound in bounded cycles. The product is meant to feel obvious on day
one; prefer the wizard over hand-editing config.

## Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.9+** | Stdlib only for the CLI and mission runner — no `pip install` |
| **At least one provider CLI** | `grok`, `claude`, and/or `codex` on `PATH` and logged in |
| **Git** | Recommended for missions; **required** for harness worktree isolation |
| **Node.js 18+** | Optional — only for the ZComb Kanban UI |

## 1. Install Absoloop on PATH

```bash
git clone https://github.com/BLERBZ/absoloop.git
cd absoloop
export PATH="$PWD/bin:$PATH"
```

`ABSOLOOP_HOME` auto-detects from the checkout that owns `bin/absoloop`. Export
it only if you move the tree or install elsewhere.

**Windows:** add `absoloop\bin` to your User PATH (the `absoloop.cmd` shim
sets `ABSOLOOP_HOME` for you). Reopen the terminal.

## 2. Run the setup wizard

```bash
absoloop setup
```

| Step | What happens |
|---|---|
| 1 · Welcome | What Absoloop is and what you need |
| 2 · PATH | Symlink `~/.local/bin/absoloop` (Unix) or PATH instructions (Windows) |
| 3 · Providers | Detects Grok / Claude / Codex + install & login hints |
| 4 · Defaults | Writes `~/.absoloop/absoloop.toml` + Codex Micro tip |
| 5 · Gitignore | Asks to add `.absoloop/` to this project's `.gitignore` (recommended) |
| 6 · Ready | Your first command — optionally start a mission immediately |

Flags:

```bash
absoloop setup -y          # non-interactive best effort
absoloop setup --force     # run again even if completed
absoloop setup --check     # exit 0 if completed (scripts/CI)
absoloop setup --reset     # clear saved setup state
```

First time you type bare `absoloop` in a terminal, you’ll be offered the
wizard automatically (Enter = setup · `s` = skip · `q` = quit).

## 3. Install at least one provider

| Provider | Typical install | Login |
|---|---|---|
| Grok Build | `curl -fsSL https://x.ai/cli/install.sh \| bash` | `grok login` |
| Claude Code | [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code/overview) | `claude login` |
| Codex | `npm i -g @openai/codex` | `codex login` |

Confirm with:

```bash
absoloop doctor
absoloop providers        # capability matrix (harness)
```

`doctor` reports PATH, versions, auth hints, gate command, and Codex Micro tips
without reading credential file contents.

## 4. Start a mission

```bash
absoloop "Make all tests pass"
```

Review the Mission Briefing card → **Enter** launches. Keys:

| Key | Action |
|---|---|
| `Enter` | Launch |
| `o` | Edit objective |
| `e` | Cycle engine |
| `m` | Cycle / set model |
| `d` | Cycle delivery (`local` / `git` / `out`) |
| `n` | Rename project |
| `g` | Preview `/goal` contract |
| `q` | Abort |

Skip the card with `-y`. Scaffold only with `--no-start`.

## 5. While it runs / after

```bash
absoloop watch     # live terminal dashboard
absoloop zcomb     # browser Kanban UI for a running mission (Node.js 18+)
absoloop status    # snapshot + next command
absoloop report    # Markdown + lite viewer
absoloop approve   # accept at the human gate
absoloop reject "guidance for the next iteration"
```

Tip: `absoloop --zcomb` (or `absoloop "…" --zcomb`) runs the same Mission
Briefing / launch as bare `absoloop`, then opens the Kanban alongside the loop.

Exit codes from the runner: `0` completed · `3` awaiting approval ·
`2` stopped safely (budget / abort / blocked).

When a mission stops at the human gate, Absoloop plays a short **chime** and
desktop banner when the OS supports it. Silence with `ABSOLOOP_CHIME=0`.

## Codex Micro

After setup, map Micro keys to shell macros (works on every OS):

```bash
absoloop shortcuts layout
absoloop shortcuts export --format input -o micro-input.md
absoloop do status
```

Full guide: [shortcuts.md](shortcuts.md).

## Next steps

- Mission loop deep dive → [mission-loop.md](mission-loop.md)
- Race / council / review → [multi-provider.md](multi-provider.md)
- Nightly / weekly segments → [schedule.md](schedule.md)
