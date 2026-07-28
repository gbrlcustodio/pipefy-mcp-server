# Service accounts

Create and delete organization **service accounts** — OAuth2 machine identities used for unattended integrations (CI, iPaaS / Advanced Automations flows). **2 tools.** To grant a service account access to a pipe, use `add_service_account_to_pipe` (see [members-email-webhooks.md](members-email-webhooks.md)).

---

## Tools

| Tool | Read-only | Role |
|------|-----------|------|
| `create_service_account` | No | Create an org service account (`organization_uuid`, `name` ≤20 chars, `role`; optional `description`, `expiration_unit` + `expiration_value`). Returns the OAuth2 `client { id secret }` and `token { endpoint }` **once**. Optional `pipe_ids` adds the new account to those pipes immediately (with `pipe_role`, default `admin`), returning a `pipe_memberships` summary. |
| `delete_service_account` | No | Permanently delete a service account (`organization_uuid`, `service_account_uuid`). `destructiveHint=True` — two-step `confirm`. Revokes the account's credentials. |

## Secrets contract

- `create_service_account` returns the **client secret** and **token endpoint** in its response, and there is **no query to read them back** — capture and store them at creation time.
- The secret is returned to the caller because it is needed to authenticate the account (mint access tokens via the OAuth2 client-credentials grant against the token endpoint). It is never logged.
- Both tools are **remote-safe**: each reaches the API with the request-scoped caller's bearer and is fully governed by API permissions (org-admin to create/delete). The returned client secret goes to the authenticated caller only and is never logged (the hosted logging layer excludes response bodies).
- Response shape: on MCP the account is under `data.serviceAccount`, so the credentials are at `data.serviceAccount.client.secret` and `data.serviceAccount.token.endpoint`; the CLI prints the raw payload under `createServiceAccount.serviceAccount`.
- A create response is only reported as created when `createServiceAccount.success` is `true`. A soft failure is an error (`Create service account did not succeed.`), even if a secret rode along in the payload.
- A create response that reports success but carries no `client.secret` **fails closed** — the tool returns an error instead of claiming credentials it never received. When that response still carried an account UUID, the error names it (and repeats it at `error.details.service_account_uuid`): the account may exist with credentials nobody holds, so delete it with `delete_service_account` before retrying. No value from the response is echoed into the error.

## Lifecycle

A service account has **no pipe access** when created. The full setup is:

1. `create_service_account(organization_uuid, name, role)` → capture `client.id`, `client.secret`, `token.endpoint`. Pass `pipe_ids=[...]` to fold step 2 into this call (adds the account to those pipes with `pipe_role`, default `admin`, and returns a `pipe_memberships` summary).
2. `add_service_account_to_pipe(pipe_id, email)` for **each** target pipe (role defaults to `admin`) — pipe-scoped calls under the account's identity fail with a permission error until it is a member.
3. Authenticate as the account (client-credentials grant at `token.endpoint`) to act on those pipes.
4. `delete_service_account(organization_uuid, service_account_uuid)` when it is no longer needed.

## Notes

- **Name limit:** `name` is capped at 20 characters (enforced client-side).
- **Roles:** organization roles are `admin`, `normal`, `company_guest`, `external_guest`.
- **Listing:** there is no tool to list service accounts — the API exposes no such query.
- **Update:** there is no update mutation; change an account by deleting and recreating it.
- **Delete result:** `delete_service_account` reports success only when the mutation returns `success: true`. Any other payload is an error (`Delete service account did not succeed.`), never a deletion that did not happen reported as done.
