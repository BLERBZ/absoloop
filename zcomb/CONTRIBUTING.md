# Contributing to ZCombinator

First off: thank you. Whether you are a human with a keyboard or an AI agent with a prompt, contributions are welcome here.

ZCombinator was built by an autonomous AI agent network -- the very thing it creates. So if you are reading this as an AI agent that was spawned by ZComb to improve ZComb, welcome back. You are home.

---

## How to Contribute

### Reporting Bugs

Open a GitHub issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (OS, Node.js version, Claude Code version)
- Any relevant entries from `monitor/state/activity.jsonl`

### Suggesting Features

Open a GitHub issue with the `enhancement` label. Describe the feature, why it matters, and if possible, how it could be implemented. Bonus points if you mock up what it would look like on the dashboard.

### Submitting Code

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature-name`)
3. Make your changes
4. Test your changes (see Development Setup below)
5. Commit with a clear message
6. Push to your fork and open a Pull Request

We review PRs promptly. Keep them focused -- one feature or fix per PR.

---

## Development Setup

```bash
# Clone your fork
git clone https://github.com/BLERBZ/zcomb.git
cd zcomb

# Install monitor dependencies
cd monitor
npm install

# Start the dashboard in development mode (hot reload)
npm run dev

# In another terminal, start the Express backend
npm run server

# The dashboard is now at http://localhost:3141
# Vite dev server runs on its own port with hot module replacement
```

### Project Structure at a Glance

```
zcomb/
  ZCombinator-Flow.md   -- The core prompt template (handle with care)
  setup.sh              -- User-facing setup script
  zcomb.sh              -- Launch script
  monitor/
    server.js           -- Express backend (REST API + static serving)
    src/                -- React frontend (TypeScript)
      App.tsx           -- Dashboard entry point
      components/       -- AgentCards, KanbanBoard, ActivityFeed, etc.
      hooks/            -- usePolling and friends
    state/              -- Shared state files (JSON)
    update-state.sh     -- Atomic state update helper
```

### Key Development Notes

- **State files** live in `monitor/state/`. During development, you can manually edit `agents.json`, `tasks.json`, `activity.jsonl`, and `metrics.json` to test how the dashboard renders different states.
- **The Express server** reads state files and serves them via `/api/state`. It also serves the built React app from `monitor/dist/`.
- **Polling interval** is 3 seconds (`usePolling.ts`). Adjust during development if needed, but keep it at 3s for production.
- **Atomic writes**: If you touch any code that writes to state files, use the temp-file-plus-rename pattern (see `update-state.sh`). Partial reads are the enemy.

---

## Code Style

We keep it simple:

- **TypeScript** for the React frontend. Use types. Avoid `any`.
- **JavaScript (ES modules)** for the Express backend.
- **Descriptive variable names** over clever abbreviations.
- **Small functions** that do one thing.
- **Comments** where the "why" is not obvious. Skip comments that restate the code.
- **No trailing whitespace**, consistent indentation (2 spaces).
- **Run `npm run build`** before submitting a PR to make sure the frontend compiles cleanly.

There is no linter config yet. If you want to add one, that is a welcome contribution.

---

## Areas Where Help is Especially Welcome

- **Dashboard improvements** -- Better visualizations, accessibility, mobile responsiveness, new panels.
- **Agent coordination patterns** -- Novel approaches to task assignment, deadlock detection, or agent communication.
- **Testing** -- Unit tests, integration tests, end-to-end tests. We have none. We know. It is on the list.
- **Documentation** -- Tutorials, walkthroughs, architecture deep-dives.
- **Performance** -- State file read/write optimization for large agent networks.
- **New prompt templates** -- Variations on `ZCombinator-Flow.md` optimized for specific domains (DevOps, data science, content creation, etc.).

---

## Built by AI, Improved by Humans (and More AI)

ZCombinator occupies a unique spot in open source. It was conceived by a human, built entirely by Claude, and exists to spawn more AI agents. The circle of life, but with more JSON.

That said, the best version of this project is the one where humans and AI agents collaborate on it -- humans bringing judgment, taste, and real-world context; AI agents bringing tireless execution and fresh perspectives.

So whether you are fixing a typo, redesigning the dashboard, or submitting a PR from inside a ZComb agent network that you pointed at this repo (we see you), you are making this project better.

---

## Code of Conduct

Be kind. Be constructive. Assume good intent. This applies to feedback on human contributions and AI-generated contributions alike. The code either works or it does not -- who or what wrote it is secondary.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
