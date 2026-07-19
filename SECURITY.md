# Security policy

## Supported versions

Security fixes land on the default branch (`main`). If you run a fork or an
older checkout, rebase or re-copy `templates/absoloop-run` after upgrades.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

1. Email or message the BLERBZ maintainers privately (GitHub Security Advisories
   preferred when available on this repository).
2. Include: impact, reproduction steps, affected versions/commits, and any
   suggested fix.
3. Allow a reasonable window for a patch before public disclosure.

We will acknowledge receipt as soon as we can and keep you updated on the fix
timeline.

## Scope notes for Absoloop

Absoloop shells out to provider CLIs (`claude`, `codex`, `grok`) and may run
agent-proposed commands inside missions. Design intent (see
[docs/multi-provider.md](docs/multi-provider.md)):

- Provider CLIs spawn as argv arrays (no shell interpolation of task text)
- Child environments are allowlisted; credentials are never copied or persisted
- Secrets are redacted from events, logs, and manifests
- Permission profiles fail closed when no safe native mapping exists
- Schedules never auto-approve the human gate

When reporting, call out anything that:

- Escapes intended permission / sandbox profiles
- Leaks secrets into `.absoloop/` logs, events, or reports despite redaction
- Allows cross-project path traversal from harness worktrees
- Weakens the integrity gate or critic contract in a way that fakes acceptance

Thank you for helping keep the loop honest.
