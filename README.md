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
