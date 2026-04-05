# Organization

Fetch organization details directly by ID. **1 tool.**

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_organization` | Yes | Fetches org details: `id`, `uuid`, `name`, `planName`, `role`, `membersCount`, `pipesCount`, `createdAt`. |

## Why a dedicated tool?

The organization ID is required by many tools (reports, automations, observability) but previously had no direct fetch path. Agents had to derive it through multi-step workarounds:

1. `search_pipes` or `get_pipe` to find a pipe in the org
2. Extract the org ID from the pipe response
3. Use the org ID in the actual tool call

`get_organization` eliminates this pattern. If you already know the org ID (from a prior `search_pipes` call or the Pipefy URL), use it directly.

## Discovering the org ID

- From `search_pipes`: the response groups pipes by organization; each org includes `id` and `name`.
- From the Pipefy URL: the org ID is the numeric segment in `https://app.pipefy.com/organizations/<org_id>/...`.
