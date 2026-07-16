# Absoloop shortcuts — keyboard & Codex Micro

Absoloop exposes a single **action catalog** that can be fired two ways:

1. **Commands** — `absoloop do <action>` (best for shell macros / Input “run command”)
2. **Chords** — map Micro keys to HID shortcuts, then `absoloop shortcuts listen`

The [Work Louder Codex Micro](https://worklouder.cc/codex-micro) is a standard
HID keyboard (13 keys, dial, joystick). Keymaps live **on the device** via
Input / Codex remapping — Absoloop never talks USB to the pad. That matches
Work Louder’s model: customize on desktop, use anywhere.

## Quick start

```bash
absoloop shortcuts list              # all actions + chords
absoloop shortcuts layout            # Codex Micro key map (mission layer)
absoloop shortcuts layout --layer harness
absoloop do status                   # fire an action from any shell
absoloop shortcuts listen            # terminal listens for F13–F24 / line protocol
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
| K3 | `report` | `f15` | complete log |
| K4 | `goal` | `f16` | goal contract |
| K5 | `approve` | `f17` | accept |
| K6 | `reject` | `f18` | reject (prompts for text) |
| K7 | `resume` | `f19` | continue |
| K8 | `extend` | `ctrl+shift+alt+e` | extend completed mission |
| K9 | `brief` | `f20` | new mission briefing |
| K10 | `cancel` | `f21` | cancel live harness run |
| K11 | `doctor` | `f22` | doctor |
| K12 | `inspect` | `f23` | inspect runs |
| K13 | `run` | `f24` | harness run |

Defaults use **F13–F24** so normal typing never collides — Ideal for macropads.

### Two Input binding styles

**A. Keyboard shortcut (listener)**  
Map each Micro key → the chord above, keep a terminal on:

```bash
absoloop shortcuts listen
```

**B. Shell macro (no listener)**  
Map each Micro key → Run Shortcut / Shell:

```bash
absoloop do status
absoloop do approve --yes
absoloop do reject --text "use the v2 API"
```

Style B is usually simpler with Codex Micro + Input.

## Line protocol

Pipes and text-emitting macros can speak to `shortcuts listen`:

```
action:status
chord:f13
watch
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
