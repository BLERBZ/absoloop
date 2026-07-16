#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
#  ZCombinator Launch Script
#  Starts the monitoring dashboard and launches the
#  autonomous agent swarm via Claude Code CLI.
# ─────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors ───────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_DIR="${SCRIPT_DIR}/monitor"

DEFAULT_OBJECTIVE="Build a full-stack todo app with a Node.js API, React frontend, SQLite persistence, user authentication, and comprehensive tests."

# ── Parse flags ──────────────────────────────────────────
NO_BROWSER=false
OBJECTIVE=""

for arg in "$@"; do
    case "$arg" in
        --no-browser)
            NO_BROWSER=true
            ;;
        *)
            if [ -z "$OBJECTIVE" ]; then
                OBJECTIVE="$arg"
            fi
            ;;
    esac
done

# ── Banner ───────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}  ╔═══════════════════════════════════╗${RESET}"
echo -e "${CYAN}${BOLD}  ║        ZCombinator Launcher        ║${RESET}"
echo -e "${CYAN}${BOLD}  ╚═══════════════════════════════════╝${RESET}"
echo ""

# ── 1. Interactive objective input ───────────────────────
if [ -z "$OBJECTIVE" ]; then
    echo -e "  ${BOLD}What is your objective?${RESET}"
    echo -e "  ${DIM}Press Enter to use the default:${RESET}"
    echo -e "  ${DIM}${DEFAULT_OBJECTIVE}${RESET}"
    echo ""
    echo -ne "  ${CYAN}▸${RESET} "
    read -r USER_INPUT
    echo ""
    if [ -n "$USER_INPUT" ]; then
        OBJECTIVE="$USER_INPUT"
    else
        OBJECTIVE="$DEFAULT_OBJECTIVE"
        echo -e "  ${DIM}Using default objective.${RESET}"
        echo ""
    fi
fi

# ── 2. Start the Dashboard ──────────────────────────────
echo -e "  ${BOLD}Starting monitoring dashboard...${RESET}"

# Kill any existing server on port 3141
if lsof -ti:3141 &>/dev/null; then
    echo -e "  ${DIM}Stopping existing process on port 3141...${RESET}"
    lsof -ti:3141 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Build and start the server in the background
cd "${MONITOR_DIR}"
npm run start > /tmp/zcomb-dashboard.log 2>&1 &
DASHBOARD_PID=$!
cd "${SCRIPT_DIR}"

echo -e "  ${DIM}Dashboard PID: ${DASHBOARD_PID}${RESET}"

# ── 3. Wait for Dashboard ───────────────────────────────
echo -e "  Waiting for dashboard to be ready..."

MAX_WAIT=30
WAITED=0
while ! curl -s -o /dev/null -w '' http://localhost:3141 2>/dev/null; do
    sleep 1
    WAITED=$((WAITED + 1))
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo -e "  ${RED}Dashboard failed to start after ${MAX_WAIT}s.${RESET}"
        echo -e "  ${DIM}Check logs: /tmp/zcomb-dashboard.log${RESET}"
        kill "$DASHBOARD_PID" 2>/dev/null || true
        exit 1
    fi
done

echo -e "  ${GREEN}✔${RESET}  Dashboard running at ${CYAN}http://localhost:3141${RESET}"
echo ""

# ── 4. Open Browser ─────────────────────────────────────
if [ "$NO_BROWSER" = false ]; then
    if command -v open &>/dev/null; then
        open "http://localhost:3141"
        echo -e "  ${GREEN}✔${RESET}  Opened dashboard in your browser"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:3141"
        echo -e "  ${GREEN}✔${RESET}  Opened dashboard in your browser"
    else
        echo -e "  ${YELLOW}⚠${RESET}  Could not auto-open browser. Visit ${CYAN}http://localhost:3141${RESET} manually."
    fi
else
    echo -e "  ${DIM}Browser auto-open skipped (--no-browser).${RESET}"
fi

echo ""

# ── 5. Build the ZCombinator Prompt ─────────────────────
read -r -d '' ZCOMB_PROMPT << 'PROMPT_TEMPLATE' || true
ZCOMBINATOR AUTONOMOUS AGENT NETWORK

You are a Lead Architect executing a multi-agent project with live monitoring. You are tasked, but not limited to: Researching, planning, and implementing a ZCombinator-style autonomous agent network for orchestration, queues, collaboration, and high performance, centered on perfectly aligned agent roles that execute every step toward the primary objective. Draw from Claude Agent Teams best practices—including shared task lists, dependencies, direct teammate messaging, plan approval hooks, local persistence, and parallel independent work. Following the primary objective and execution model, complete all phases from execution model.

PRIMARY OBJECTIVE

**__OBJECTIVE_PLACEHOLDER__**

Execution Model

You operate in Claude Code CLI. You have access to:
- **Agent tool**: Spawn real subagents (teammates) for parallel work
- **Bash tool**: Run servers, build tools, execute scripts
- **File I/O**: Write persistence state, configs, UI code to disk

Phase 0: Monitoring Infrastructure (DO THIS FIRST)
The monitoring dashboard is already running at http://localhost:3141. The state directory is at monitor/state/. Write to agents.json, tasks.json, activity.jsonl, and metrics.json as you work.

Dashboard Enhancement Protocol
If the dashboard already exists (monitor/src/ has React components), analyze the current UI/UX and create tasks to improve it. Every ZComb run should leave the dashboard better than it found it. See ZCombinator-Flow.md for the full enhancement checklist.

Phase 1-6: Follow the full ZCombinator execution model
See ZCombinator-Flow.md for the complete phase definitions. Execute all phases from Research & Scoping through Validation & Closure.
PROMPT_TEMPLATE

# Substitute the objective into the prompt
ZCOMB_PROMPT="${ZCOMB_PROMPT//__OBJECTIVE_PLACEHOLDER__/${OBJECTIVE}}"

# ── 6. Display summary and launch ───────────────────────
echo -e "  ${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  ${BOLD}Objective:${RESET}"
echo -e "  ${CYAN}${OBJECTIVE}${RESET}"
echo -e "  ${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${GREEN}${BOLD}Launching Claude Code with ralph-loop...${RESET}"
echo ""
echo -e "  ${DIM}Dashboard logs: /tmp/zcomb-dashboard.log${RESET}"
echo -e "  ${DIM}To stop the dashboard later: kill ${DASHBOARD_PID}${RESET}"
echo ""

# ── 7. Execute Claude Code ──────────────────────────────
RALPH_LOOP_CMD="/ralph-loop:ralph-loop \"${ZCOMB_PROMPT}

  Output FULLY COMPLETE only after 100 percent objective fulfillment, all tasks closed, and validation passed with zero open issues.\" --max-iterations 5000 --completion-promise \"FULLY COMPLETE\""

exec claude "${RALPH_LOOP_CMD}"
