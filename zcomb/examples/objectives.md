# ZCombinator Example Objectives

Drop any of these into the `<YOUR OBJECTIVE HERE>` slot in the ZCombinator prompt and watch the swarm go.

---

### 1. Real-Time Multiplayer Trivia App

```
Build a real-time multiplayer trivia web app with: a Node.js + WebSocket backend that hosts game rooms, a React frontend with live scoreboards and countdown timers, a question bank of 200+ questions across 6 categories seeded from Open Trivia DB, player authentication via magic-link email, anti-cheat timing validation, and a post-game stats screen with per-player accuracy charts. Deploy-ready with Docker Compose.
```

### 2. `brainrot` — A CLI That Roasts Your Code

```
Create a CLI tool called "brainrot" (installable via npm -g) that accepts a file path or piped stdin, performs static analysis on the code, and outputs brutally honest but constructive feedback with a comedic tone. Support JavaScript, TypeScript, Python, and Go. Include severity ratings (cringe / sus / unhinged / fire), a --json flag for CI integration, a --fix flag that auto-applies suggestions where possible, and a config file (.brainrotrc) for custom rules. Ship with 40+ built-in rules and a plugin API for community extensions.
```

### 3. Event-Driven Analytics Pipeline

```
Build an event-driven data pipeline that ingests clickstream events via an HTTP collector endpoint, validates and enriches events with GeoIP and user-agent parsing, routes them through a local Redis Streams queue, processes them with a pool of worker consumers that compute sessionization and funnel metrics, stores aggregated results in SQLite, and exposes a REST API serving pre-computed dashboards (top pages, conversion funnels, real-time active users). Include a load-test harness that simulates 10k events/sec and a Grafana-compatible metrics exporter.
```

### 4. Self-Healing Microservice Mesh

```
Design and implement a local microservice mesh with 4 services (API Gateway, User Service, Order Service, Notification Service) communicating over HTTP. Build a mesh sidecar process that handles service discovery via a shared registry file, automatic retries with exponential backoff, circuit breaking, and health-check-driven traffic rerouting. Include a chaos monkey script that randomly kills services, and verify the mesh recovers within 5 seconds. All services in TypeScript, full integration test suite, and a terminal UI showing live service topology and request flow.
```
