# Absoloop documentation

**Motto:** Synergetic Loops

**AbsoLoop** is Synergetic Loops — bounded cycles where builder, critic, human,
and local agent CLIs (Grok Build, Claude Code, Codex) compound so the mission
outcome is stronger than any single agent alone.

These guides cover setup, the mission repair loop, the multi-provider harness,
schedules, shortcuts, and brand assets. Start at the root
[README](../README.md) for the product overview, then pick a guide below.

## Guides

| Doc | Audience | Contents |
|---|---|---|
| [getting-started.md](getting-started.md) | New operators | Setup wizard, PATH, providers, first mission |
| [mission-loop.md](mission-loop.md) | Day-to-day use | Mission Briefing, `/goal`, skills, delivery, watch/report, ZComb |
| [multi-provider.md](multi-provider.md) | Harness users | `run` / `build` / `review`, cancel, apply, security |
| [architecture/multi-provider-harness.md](architecture/multi-provider-harness.md) | Contributors | Adapter contract, event model, worktrees, gates |
| [schedule.md](schedule.md) | Long missions | Cron / interval triggers (never auto-approves) |
| [shortcuts.md](shortcuts.md) | Power users | Keyboard chords + Codex Micro |
| [assets/BRAND.md](assets/BRAND.md) | Design / docs | Logos, palette, voice |
| [github-profile/SETUP.md](github-profile/SETUP.md) | Maintainers | Publish the org/personal GitHub profile |

## Mental model

```text
Mission loop (default)
  objective → /goal → builder ↔ critic → human gate → delivery

Harness (one-shot / multi-agent)
  task → isolated worktree(s) → provider stream → deterministic gates → patch
```

Both surfaces share provider adapters, permission profiles, and secret
redaction. The mission loop owns checkpointed budgets and the adversarial
critic; the harness owns race/council selection and worktree isolation.

## Related

- Optional Kanban UI: [zcomb/README.md](../zcomb/README.md)
- Contributor guide: [CONTRIBUTING.md](../CONTRIBUTING.md)
- Security reports: [SECURITY.md](../SECURITY.md)
- Code of conduct: [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)
