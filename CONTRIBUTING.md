# Contributing to Absoloop

Thanks for helping build a bounded, auditable AI repair loop. This guide gets
you from clone → useful PR without tribal knowledge.

## Quick start for contributors

```bash
git clone https://github.com/BLERBZ/absoloop.git
cd absoloop
# ABSOLOOP_HOME auto-detects from bin/; export only if you move the tree
export PATH="$PWD/bin:$PATH"          # Windows: add bin\ to PATH

# Offline suite (no provider credentials required) — Linux/macOS/Windows
python -m unittest discover -s tests -v
# or
python -m pytest tests -q

absoloop doctor   # env + Grok/Claude/Codex auth hints + Codex Micro tips
```

Optional live smokes (credentials + provider CLIs required):

```bash
ABSOLOOP_LIVE_SMOKE=1 ABSOLOOP_SMOKE_CLAUDE=1 \
  python3 -m unittest tests.test_harness_workflows.LiveSmoke
```

## Project map

| Path | Role |
|---|---|
| `bin/absoloop` | Public CLI (mission briefing, status/watch/report, harness entry) |
| `templates/absoloop-run` | Loop runner copied into mission projects |
| `absoloop_harness/` | Multi-provider harness (Grok / Claude / Codex) |
| `templates/skills/` | Loopers-toolbox skills seeded into projects |
| `tests/` | Characterization + harness tests (stdlib unittest / pytest) |
| `docs/` | User guides + architecture |

## Design constraints (read before coding)

1. **Stdlib-first** — `bin/absoloop` and `templates/absoloop-run` must stay
   pure Python 3.9+ with no third-party runtime deps.
2. **Evidence over narrative** — acceptance paths go through integrity →
   critic → human gate. Do not weaken those for convenience.
3. **Provider-native** — adapters wrap CLIs; they do not reimplement auth,
   tools, or sandboxing.
4. **Characterization tests protect the loop** — if you change runner or CLI
   behavior, update or add tests under `tests/test_characterization_*`.
5. **Match local style** — small focused diffs; no drive-by refactors.

## Good first contributions

- Docs fixes and clearer examples in `docs/`
- New characterization coverage for edge cases you hit
- Provider adapter hardening (version probes, resume, cancel)
- Shortcut catalog / Micro layout improvements (`docs/shortcuts.md`)
- Report viewer polish (`absoloop_harness/report_doc.py`)

## Pull request checklist

- [ ] `python3 -m unittest discover -s tests` passes
- [ ] New behavior has a test (or a clear reason it cannot)
- [ ] User-facing changes noted in the PR description
- [ ] No secrets, API keys, or personal mission state committed
- [ ] Runner template changes considered for existing missions
      (re-adoption / copy notes)

## Commit & PR style

- Prefer short, imperative commit subjects focused on *why*
- One concern per PR when possible
- Link issues with `Fixes #123` when applicable

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Questions

Open a Discussion or Issue with the `question` label. For security-sensitive
topics, follow [SECURITY.md](SECURITY.md).
