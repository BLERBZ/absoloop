# Getting started

Absoloop is meant to feel obvious on day one. Prefer the wizard over
hand-editing config.

## 1. Install Absoloop on PATH

```bash
git clone https://github.com/BLERBZ/absoloop.git
cd absoloop
export PATH="$PWD/bin:$PATH"
```

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
| 5 · Ready | Your first command — optionally start a mission immediately |

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
```

## 4. Start a mission

```bash
absoloop "Make all tests pass"
```

Review the Mission Briefing card → **Enter** launches. Keys: `o` objective ·
`e` engine · `d` delivery · `n` rename · `g` preview `/goal` · `q` abort.

## 5. While it runs / after

```bash
absoloop watch     # live dashboard
absoloop status    # snapshot + next command
absoloop report    # Markdown + lite viewer
absoloop approve   # accept at the human gate
```

## Codex Micro

After setup, map Micro keys to shell macros (works on every OS):

```bash
absoloop shortcuts layout
absoloop shortcuts export --format input -o micro-input.md
absoloop do status
```

Full guide: [shortcuts.md](shortcuts.md).
