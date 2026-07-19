<!--
  Absoloop / BLERBZ — GitHub profile README
  ========================================
  Publish this file as the profile README for the BLERBZ organization
  (or adapt for a personal username/username repo).

  Org install (recommended):
    1. Create a public repo named exactly: .github
       under https://github.com/BLERBZ
    2. Add this file at: profile/README.md
    3. Copy brand images next to it (or keep relative paths working):
         profile/absoloop-logo.png
         profile/absoloop-logo-pixel.png
    4. Push to the default branch — the org profile updates within a few minutes.

  Personal install:
    1. Create a public repo named exactly your username
    2. Put this content in README.md at the repo root
    3. Adjust links if you are not under the BLERBZ org

  Brand source of truth in the Absoloop repo:
    docs/assets/ + docs/assets/BRAND.md
-->

<p align="center">
  <img src="absoloop-logo.png" alt="Absoloop" width="460" />
</p>

<h1 align="center">BLERBZ</h1>

<p align="center">
  <strong>Tools that keep AI honest.</strong><br/>
  Open source systems for bounded agent loops, evidence gates, and local CLIs —
  not another chatbot wrapper.
</p>

<p align="center">
  <a href="https://github.com/BLERBZ/absoloop">Absoloop</a> ·
  <a href="https://github.com/BLERBZ/absoloop/blob/main/CONTRIBUTING.md">Contribute</a> ·
  <a href="https://github.com/BLERBZ/absoloop/blob/main/docs/assets/BRAND.md">Brand</a>
</p>

---

## Flagship · Absoloop

**Motto:** Synergetic Loops

**AbsoLoop** is Synergetic Loops — bounded cycles where builder, critic, human,
and local agent CLIs compound so the outcome is stronger than any single agent
alone. A run is not “done” until the builder’s evidence survives an independent
critic **and** a human gate — under hard budgets you can resume or extend.

```text
objective → /goal → iterate → integrity → critic → you approve → deliver
```

| | |
|---|---|
| **Providers** | Grok Build · Claude Code · Codex |
| **Runtime** | Python 3.9+ stdlib — no pip tax for the core loop |
| **License** | MIT |

<p align="center">
  <a href="https://github.com/BLERBZ/absoloop">
    <img src="https://img.shields.io/badge/github-BLERBZ%2Fabsoloop-00cde1?style=for-the-badge&labelColor=0c1118" alt="Absoloop on GitHub" />
  </a>
</p>

```bash
git clone https://github.com/BLERBZ/absoloop.git
cd absoloop && export ABSOLOOP_HOME="$PWD"
ln -sf "$PWD/bin/absoloop" ~/.local/bin/absoloop
absoloop "Make all tests pass"
```

<p align="center">
  <img src="absoloop-logo-pixel.png" alt="Absoloop pixel mark" width="260" />
</p>

## What we care about

- **Receipts over vibes** — ledgers, reports, critic findings, cancelable runs  
- **Provider-native power** — we wrap CLIs; we don’t fake their sandboxes  
- **Contributor-ready** — tests offline, clear CONTRIBUTING, no mystery deps  
- **Human in the loop** — approval is a feature, not a failure mode  

## Join in

| Start here | Link |
|---|---|
| Clone & test | [CONTRIBUTING.md](https://github.com/BLERBZ/absoloop/blob/main/CONTRIBUTING.md) |
| Report a bug | [Issue templates](https://github.com/BLERBZ/absoloop/issues/new/choose) |
| Security | [SECURITY.md](https://github.com/BLERBZ/absoloop/blob/main/SECURITY.md) |
| Code of conduct | [CODE_OF_CONDUCT.md](https://github.com/BLERBZ/absoloop/blob/main/CODE_OF_CONDUCT.md) |

```bash
python3 -m unittest discover -s tests   # no credentials required
```

---

<p align="center">
  <sub>MIT · Built in the open · Infinity optional, integrity required</sub>
</p>
