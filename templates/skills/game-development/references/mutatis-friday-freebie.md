# Mutatis Friday Freebie — AbsoLoop routing

Use this when the mission is mutatis.ai **Friday Freebie**: weekly hybrid
Pixi/Three instant-play games, Friday 00:00 America/New_York rotation, never
repeat prior Freebies.

## Map orchestrator routes → installed skills

Upstream sub-skills (`game-development/web-games`, `…/game-design`, etc.) are
not bundled. On mutatis, route to these project skills instead:

| Orchestrator need | Use skill |
|---|---|
| Web / HTML5 / WebGL target | This skill (core principles) + `technical-artist` |
| 2D sprites / Pixi gameplay | `technical-artist` + game module under `static/friday-freebie/games/` |
| 3D / Three backdrop / depth fantasy | `technical-artist` (Three only when depth is the fantasy) |
| GDD, balancing, player psychology | `game-designer` |
| Encounter density / difficulty curves | `level-designer` |
| Visual style, particles, juice, FPS budget | `technical-artist` + `ai-game-art-pipeline` (runtime art) |
| SFX / music / adaptive audio | `game-audio` |
| Title, tagline, onboarding copy | `narrative-designer` |

## Multi-level upgrade bar (ship-ready)

When asked to raise a Freebie "multiple levels," do all of the following —
not just one number tweak:

1. **Teach → test → punish** spawn/difficulty curve (`level-designer`)
2. **Readable telegraphs** before lethal hits; mobile-safe spacing
3. **Juice stack**: hit-pause, shake, particles, trails, SFX (`technical-artist`, `game-audio`)
4. **Score milestones** that unlock distinct phases (not a flat ramp)
5. **60 FPS budget** from this skill's performance table; no GC spikes in hot loops
6. **Fixed-timestep feel** for physics-y verbs; interpolate render
7. **Object pooling** for rocks/crystals/projectiles

## Ship paths

- Live / queue: `static/friday-freebie/{manifest,next,archive,allowlist}.json`
- Games: `static/friday-freebie/games/<slug>.js` → `window.FF_GAME.create(api)`
- Validate: `python3 scripts/ff_rotate.py --dry-run`
- Tests: `pytest tests/test_friday_freebie.py`
- Browser smoke: `python3 scripts/ff_browser_smoke.py` when present
- Mirror: keep `public/static/friday-freebie/` in sync after edits

## Tomorrow's release posture

If rotation is imminent (Friday 00:00 ET):

1. Confirm queue head in `next.json` is the ship candidate (entry + cover present)
2. Elevate that game first to the multi-level bar above
3. Then raise the rest of the staged set so the following weeks stay ahead
4. Never weaken tests; never clone fingerprints/`gameId`s from `archive.json`
