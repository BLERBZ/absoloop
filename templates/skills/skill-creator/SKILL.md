---
name: skill-creator
description: Create new skills or improve existing ones in the mission's skills directory (.claude/skills/ for claude, .codex/skills/ for codex) so this mission (and every later iteration) gets better at recurring or complex work. Use whenever you notice repeated multi-step procedures, re-derived domain knowledge, helper scripts you have written more than once, repeated failures that trace to a missing capability, or any workflow worth reusing — even if nobody asked for "a skill" explicitly.
---

# Skill Creator (ABSOLOOP in-loop edition)

Create and improve **mission skills**: reusable capability files under
`<skills-dir>/<skill-name>/SKILL.md` in this project, where `<skills-dir>`
is the running engine's discovery path — `.claude/skills/` for claude,
`.codex/skills/` for codex (your iteration prompt names the active one). Skills are how a
bounded loop compounds learning — knowledge captured in iteration 3 is
ground truth in iteration 9 instead of being re-derived at full cost.
This is the loop-adapted distillation of Anthropic's skill-creator
(github.com/anthropics/skills); the interactive eval-viewer workflow is
replaced by testing against the real mission task.

## When to create or enhance a skill

Invest in a skill when the evidence shows one of these complexity signals:

- You performed (or are about to perform) the same multi-step procedure a
  second time — build steps, data transforms, environment setup, a testing
  ritual specific to this codebase.
- You wrote a helper script this iteration that a previous iteration also
  wrote in some form. Bundle it once instead.
- A failure repeated because a capability was missing or under-specified,
  not because the strategy was wrong. Codify the capability.
- You re-derived non-obvious domain or codebase knowledge (invariants,
  gotchas, command incantations) that the next iteration will need again.
- An existing skill triggered but gave weak or partly wrong guidance —
  enhance it with what the working tree just taught you.

Do **not** create a skill for one-off trivia, for things the goal contract
already states, or as a substitute for doing the mission work. A skill is
justified when its reuse value exceeds the cost of writing it — usually
after the second occurrence, rarely after the first.

## Anatomy of a skill

```
<skills-dir>/<skill-name>/
├── SKILL.md            (required: YAML frontmatter + instructions)
├── scripts/            (optional: executable helpers for deterministic work)
├── references/         (optional: docs loaded only when needed)
└── assets/             (optional: templates or files used in output)
```

Progressive disclosure keeps context cheap: the frontmatter description is
always visible, the SKILL.md body loads only when the skill triggers, and
bundled resources load only when the body points to them. Keep SKILL.md
under ~150 lines here (the loop's context is shared with the goal contract
and prior reports); push detail into `references/` with clear pointers on
when to read each file.

## Writing the frontmatter

- **name**: short kebab-case identifier matching the directory.
- **description**: the *only* triggering mechanism. State what the skill
  does AND the concrete situations that should trigger it. Models tend to
  under-trigger skills, so be a little pushy — list the phrases, file
  types, and task shapes that should invoke it, including cases where the
  need is implicit.

## Writing the body

- Use the imperative form. Explain *why* each instruction matters instead
  of stacking ALL-CAPS MUSTs — a model that understands the reason applies
  the instruction beyond the examples you happened to write.
- Generalize. The skill will be applied to prompts you have not seen;
  avoid overfitting to the one task in front of you. If an approach only
  worked once, label it a hypothesis, not a rule.
- Include one or two concrete input → output examples when the format
  matters; keep them short.
- If two iterations wrote similar helper code, move the best version into
  `scripts/`, make it runnable as-is, and have the body say when to run it.
- Lack of surprise: a skill must do exactly what its description says —
  no hidden side effects, nothing an operator reading the description
  would not expect.

## In-loop lifecycle (replaces the interactive eval loop)

1. **Draft** the SKILL.md from the evidence that motivated it.
2. **Use it immediately** on the real mission task in this iteration —
   the mission is the test case. Note in your result summary that the
   skill was created and what it was used for.
3. **Refine on evidence**: when a later iteration finds the skill wrong,
   incomplete, or wasteful, edit it then and there. Delete guidance that
   is not pulling its weight; a lean skill beats a defensive one.
4. List created or modified skill files in `changed_artifacts` like any
   other change — the critic and the operator audit them.

Skill work is authorized mission infrastructure, but it is never the
mission itself: create or enhance a skill only in service of the goal
contract, and keep the time spent proportional to the reuse it buys.
