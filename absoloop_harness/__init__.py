"""Absoloop harness package — provider-neutral local agent OS.

First-class CLI backends: Grok Build, Claude Code, and Codex. This package
also hosts mission-adjacent UX that shares the same install root:

  core / process / providers / workspace / orchestrator
      Harness run pipeline (worktrees, events, gates, cancel)

  cli / config / models / delegation / runtime / spawn_evidence
      Operator surface and cross-process run control

  briefing / setup_wizard / report_doc / shortcuts / schedule / notify / zcomb
      Mission Briefing, onboarding, reports, Micro pad, cron triggers, Kanban

Keep ``bin/absoloop`` and ``templates/absoloop-run`` stdlib-only; modules
here may grow but must not force pip installs for the default mission path.
"""

__all__ = ["core", "process", "workspace", "orchestrator", "config", "cli"]
