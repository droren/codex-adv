# codex-adv

`codex-adv` is an interactive adaptive CLI that sits in front of Codex CLI and chooses between local-first and cloud execution paths, with persistent chat sessions and a richer terminal interface.

It is intentionally scoped to the foundation you outlined:

- `Codex CLI` remains the execution engine
- local and cloud providers are represented as Codex profiles
- routing stays separate from execution
- prompt rewriting stays separate from routing
- learning is historical decision support, not model training
- SQLite stores outcomes for continuous improvement

## Architecture

```text
[ User ]
   |
[ codex-adv CLI ]
   |
[ Router ]
   |
[ Rewriters ]
   |
[ Executor ]
  |       |
local   cloud
  |       |
[ Feedback + Learning ]
   |
[ SQLite Memory DB ]
```

## What v1 includes

- Interactive chat mode with persistent sessions
- Live streaming output during interactive turns
- Clean interactive result panels with muted working-state UI
- Rule-based task classification
- Local vs cloud routing
- Separate local and cloud prompt rewriters
- Thin wrappers around `codex --profile <name>`
- Failure detection and automatic cloud fallback
- SQLite request logging
- Historical success-rate summaries for future routing upgrades

## What v1 does not include

- OpenClaw integration
- advanced cost-aware scoring
- automated prompt strategy optimization
- MCP/task-planner orchestration

## Quick start

1. Create and activate a virtual environment.
2. Install the package:

```bash
pip install -e .
```

3. Make sure `codex` is available on your `PATH`.
4. Copy and adapt the sample config:

```bash
mkdir -p .codex-adv
cp config/router.example.toml .codex-adv/router.toml
```

5. Start the interactive CLI:

```bash
codex-adv
```

## Commands

```bash
codex-adv
codex-adv chat --new
codex-adv run "Fix this failing unit test"
codex-adv stats
codex-adv init
```

Inside chat:

```text
/help
/switch <id-prefix>
/rename Better title
/history
/history 10
/route
/sessions
/new Refactor session
/quit
```

## Development checks

Install the developer dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

Run the full quality gate:

```bash
make check
```

Or run each part separately:

```bash
make lint
make audit
make test
```

## Codex profiles

The executor assumes two Codex profiles exist:

- `local`
- `cloud`

Example idea:

```bash
codex --profile local "Explain this file"
codex --profile cloud "Refactor this module and add tests"
```

`codex-adv` does not replace Codex config. It routes into it and keeps interactive state in SQLite.
By default, routing is local-first and only prefers cloud for clearly heavier tasks or after poor local outcomes.

## Config

Default config location:

`./.codex-adv/router.toml`

You can override it with:

```bash
codex-adv --config /path/to/router.toml run "..."
```

## Next steps

- Upgrade router scoring using historical latency and fallback rates
- Store rewrite strategy effectiveness by task type
- Add richer failure heuristics
- Add OpenClaw as a planner only
