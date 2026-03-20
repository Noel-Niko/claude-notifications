# CLAUDE.md — claude-notifications

This repo packages the iMessage notification skill for Claude Code as an installable tool.

## Running Tests

```bash
uv run pytest -m "not integration"
```

Integration tests (require Messages.app + iMessage) are skipped by default:

```bash
uv run pytest -m integration
```

## Repo Layout

- `src/imessage-notify/` — Source scripts (copied to `~/.claude/skills/imessage-notify/` by installer)
- `tests/` — Unit and integration tests
- `docs/` — Setup guides and documentation
- `install.sh` — One-command installer
- `uninstall.sh` — Clean removal