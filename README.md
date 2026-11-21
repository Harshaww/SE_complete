# Cerebra

YouTube Video Intelligence MCP Server - Python implementation.

## Quick Start

```bash
pip install -e ".[dev]"
PYTHONPATH=src pytest tests/ --cov=cerebra     # no network needed
cerebra-cli login                              # authorise (needs GOOGLE_CLIENT_ID/SECRET)
cerebra                                        # run the MCP server over stdio
```

* [User guide](docs/user-guide.md) - setup, tools, human-approval flow, recovery, quota
* [Developer API](docs/developer-api.md) - ports, live adapter, write protocol, config
* [Architecture](docs/architecture.md) and [ADRs](docs/adr/)

Results are based on liked videos, subscriptions and playlists - NOT on watch history.

## Branching, review and releases (PR-6)

* Policy (CON-7): every change (code, skills, brain notes) is merged through a pull request
  with at least one human review and a green CI run (ruff, tests, secret scan, SKILL.md and
  brain validation, pip-audit).
* Branches: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`; commit messages carry requirement IDs.
* Releases are tagged `vMAJOR.MINOR.PATCH` on `main`; notable changes are recorded in
  [CHANGELOG.md](CHANGELOG.md).
* Live-API tests never run in PR CI (see `docs/developer-api.md`, "Live API suites").
