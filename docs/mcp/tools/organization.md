# Organization

Discover the organizations you can access, or fetch one by ID. **2 tools.**

---

| Tool | Read-only | Role |
|------|-----------|------|
| `list_organizations` | Yes | Lists organizations the caller can access — no id required. Each entry has `id`, `uuid`, `name`, `planName`, `role`, `membersCount`, `pipesCount`, `createdAt`. |
| `get_organization` | Yes | Fetches one org's details by ID: `id`, `uuid`, `name`, `planName`, `role`, `membersCount`, `pipesCount`, `createdAt`. |

**`organization_id`** (for `get_organization`) matches GraphQL: use a **string** (e.g. `"123456789"` — numeric segment from `https://app.pipefy.com/organizations/<org_id>/...` or from `list_organizations` / `search_pipes`). Unquoted JSON integers are coerced to the same string form. See [Pipefy IDs in pipes & cards](pipes-and-cards.md#pipefy-ids-type-safety).

## Discovering organizations

`list_organizations` is the zero-knowledge entry point: it answers "which organizations do I have access to?" with no id required, so it is the natural first call when onboarding to a session. The API scopes the result to the caller's own access, and an empty list means the caller belongs to no organization. Use the returned `id` / `uuid` for the tools that require one (reports, automations, observability, portals).

Other paths to an org id, when you already have context:

- From `search_pipes`: the response groups pipes by organization; each org includes `id` and `name`.
- From the Pipefy URL: the org ID is the numeric segment in `https://app.pipefy.com/organizations/<org_id>/...`.
