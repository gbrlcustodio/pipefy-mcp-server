## Summary

<!-- What changed and why (1–3 bullets). -->

-

## Test plan

<!-- How reviewers / CI can verify. -->

- [ ] `uv run pytest -m "not integration"`
- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] Manual smoke (if applicable): callable via Cursor MCP

## Docs / skills

- [ ] `docs/parity.md` updated when MCP ↔ CLI coverage changed
- [ ] Affected `skills/` updated in this PR (or a paired PR)
- [ ] No docs/skills update needed

## Legal / contributions

- [ ] Commits include DCO sign-off (`git commit -s`)
- [ ] Regulated-domain skills include `COMPLIANCE.md` when applicable
