# Absoloop shortcuts — keyboard & Codex Micro

Absoloop exposes a single **action catalog** that works the same on
**Linux, macOS, and Windows**, across mission-loop and harness workflows
(Grok / Claude Code / Codex).

Fire actions two ways:

1. **Commands** — `absoloop do <action>` ← **recommended for Codex Micro**
2. **Chords** — map Micro keys to HID shortcuts, then `absoloop shortcuts listen` (Unix TTY)

The [Work Louder Codex Micro](https://worklouder.cc/codex-micro) is a standard
HID keyboard (13 keys, dial, joystick). Keymaps live **on the device** via
Input / Codex remapping — Absoloop never talks USB to the pad.

## Out-of-the-box checklist

```bash
# 1. Install Absoloop so bin/ is on PATH (ABSOLOOP_HOME auto-detects)
#    macOS/Linux:
ln -sf "$PWD/bin/absoloop" ~/.local/bin/absoloop
#    Windows: add …\absoloop\bin to PATH (absoloop.cmd sets ABSOLOOP_HOME)

absoloop doctor                  # env + grok/claude/codex + Micro hints
absoloop shortcuts layout        # see the 13-key map
absoloop shortcuts export --format input -o micro-input.md
absoloop do status               # smoke-test any action
```

On Windows, prefer **shell macros** (`absoloop do …`). TTY chord listen needs
Unix `termios` and will automatically fall back to the line protocol.

## Quick start

```bash
absoloop shortcuts list              # all actions + chords
absoloop shortcuts layout            # Codex Micro key map (mission layer)
absoloop shortcuts layout --layer harness
absoloop do status                   # fire an action from any shell
absoloop shortcuts listen            # Unix: F13–F24 · all OS: line protocol
absoloop shortcuts export --format input -o micro-input.md
absoloop shortcuts bind watch f14    # persist to ~/.absoloop/absoloop.toml
```

## Recommended Codex Micro setup

| Control | Absoloop use |
|---|---|
| **Keys K1–K13** | Mission actions (layer 0) or harness actions (layer 1) |
| **Dial** | Input layer up/down (mission ↔ harness) |
| **Joystick** | Four custom `absoloop do …` shell macros |

### Layer 0 — Mission (defaults)

| Key | Action | Default chord | Role |
|---|---|---|---|
| K1 | `status` | `f13` | idle / status |
| K2 | `watch` | `f14` | thinking feed |
| K3 | `report` | `f15` | mission report viewer |
| K4 | `goal` | `f16` | goal contract |
| K5 | `approve` | `f17` | accept |
| K6 | `reject` | `f18` | reject (prompts for text) |
| K7 | `resume` | `f19` | continue |
| K8 | `extend` | `ctrl+shift+alt+e` | extend (fresh budgets + focus note) |
| K9 | `brief` | `f20` | new mission briefing |
| K10 | `cancel` | `f21` | cancel live harness run |
| K11 | `doctor` | `f22` | doctor |
| K12 | `inspect` | `f23` | inspect runs |
| K13 | `run` | `f24` | harness run |

Defaults use **F13–F24** so normal typing never collides — ideal for macropads.

### Two Input binding styles

**A. Shell macro (recommended — all platforms)**  
Map each Micro key → Run Shortcut / Shell:

```bash
absoloop do status
absoloop do approve --yes
absoloop do reject --text "use the v2 API"
absoloop do doctor
```

No listener required. Works in Windows Terminal, macOS Terminal, Linux.

**B. Keyboard shortcut (Unix TTY listener)**  
Map each Micro key → the chord above, keep a terminal on:

```bash
absoloop shortcuts listen
```

Decodes F13–F24 (xterm / iTerm / macOS Terminal / Windows Terminal CSI).
Modifier chords like `ctrl+shift+alt+e` are best fired via style A
(`absoloop do extend`) — TTY listen is best-effort for plain function keys.

## Line protocol

Pipes and text-emitting macros can speak to `shortcuts listen` on any OS:

```
action:status
chord:f13
watch
```

```bash
echo action:status | absoloop shortcuts listen --once
```

## Configuration

In `absoloop.toml` or `~/.absoloop/absoloop.toml`:

```toml
[shortcuts]
enabled = true
confirm_dangerous = true
status = "f13"
watch = "f14"
approve = "f17"
# clear a default: approve = ""
```

`absoloop shortcuts bind <action> <chord>` writes the user file for you.

## Dangerous actions

`approve` and `cancel` ask for confirmation when run from listen mode unless
`confirm_dangerous = false` or you pass `--yes` to `absoloop do`.

## Providers

Shortcuts and `absoloop do` are provider-agnostic. Harness actions (`run`,
`cancel`, `inspect`, `doctor`) work with whichever of **Grok**, **Claude Code**,
or **Codex** are on PATH — check with `absoloop doctor`.
