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

## Why counts disagree

`pipesCount` is the org-wide total: every pipe in the organization. Pipe listings are membership scoped: `search_pipes`, and `organization { pipes }` through `execute_graphql`, return only the pipes the calling identity is a member of. The two numbers answer different questions, so they routinely differ. In one organization a listing returned 46 pipes while `pipesCount` reported 274. Role does not widen the listing: a `super_admin` gets the same membership-scoped result as anyone else.

Truncation is a second, independent cause of a short list. `search_pipes` caps results per organization (`max_pipes_per_org`, 1 to 500, and 500 is the default) and sets `pipes_truncated` on the org entry. A pipe can be missing because the identity is not a member of it, because the cap cut it, or both.

`pipes_truncated` does not separate those two causes. It is conservative: it is also set whenever `pipesCount` exceeds the number of pipes returned, which is true on every membership-scoped listing. So a `true` flag on its own is not evidence that the cap cut anything, and on an org where the identity is a member of few pipes it will be `true` no matter how high the cap goes.

What to do:

- Treat `pipesCount` as a total, not as the expected size of a listing. Do not compare the two to decide whether a call failed.
- Read `search_limits.max_pipes_per_org` before acting on `pipes_truncated`. Raising the cap only helps if the applied cap is below 500 and the returned count reached it. When the applied cap is already 500 and the list is well under it, the cap cut nothing and membership is the cause.
- To see more pipes, list from an identity with broader access, or add the identity to the pipes it needs.
- For a wider read through `execute_graphql`, `organization { pipes(include_publics: true) }` adds pipes that are public inside the organization but that the identity is not a member of. The toolkit tools do not expose this argument. Even the widened list normally stays below `pipesCount`, so it does not reconcile the two numbers.

`pipes` returns a plain list, not a Relay connection: `first`, `edges` and `pageInfo` are rejected. The working shape is:

```graphql
query {
  organization(id: "<org_id>") {
    pipesCount
    pipes(include_publics: true) { id name }
  }
}
```
