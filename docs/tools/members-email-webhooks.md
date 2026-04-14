# Members, Email & Webhooks

Manage pipe membership, send emails from card inboxes, read inbox replies, and manage webhooks. **9 tools.**

---

## Member management

| Tool | Read-only | Role |
|------|-----------|------|
| `invite_members` | No | Invite one or more users to a pipe by email; `members` is a list of dicts with `email` and `role_name`. |
| `remove_member_from_pipe` | No | Permanently remove one or more users from a pipe (`destructiveHint=True` — confirm with the user first). |
| `set_role` | No | Set a member's role on a pipe (`member_id`, `role_name`). |

### Service Account Protection

When the optional environment variable **`PIPEFY_SERVICE_ACCOUNT_IDS`** is set to a comma-separated list of Pipefy user IDs, the server treats those IDs as **service accounts** for MCP safety:

- **`remove_member_from_pipe`** — Removal is **blocked** if any requested `user_id` is in that list. The tool returns an error explaining that removing the service account would break write operations for the pipe; use the Pipefy UI if removal is intentional. If the env var is unset or empty, this check is skipped.
- **`set_role`** — If `member_id` is a listed service account ID, the mutation still runs (role changes are reversible), but the success payload may include a **warning** reminding you to keep a role that preserves write permissions.

Configure IDs in `.env` (see `.env.example`). Omit the variable when you do not need this guard.

## Email tools

| Tool | Read-only | Role |
|------|-----------|------|
| `get_email_templates` | Yes | List email templates for a pipe or table (`repo_id`); optional `filter_by_name`. Use before `send_email_with_template` to discover template IDs. |
| `get_card_inbox_emails` | Yes | List emails (sent and received) for a card's inbox. Use `email_type: 'received'` to get only replies. |
| `send_inbox_email` | No | Send an email from a card's inbox; requires the card to have an email inbox enabled. `from_` (sender) is required. |
| `send_email_with_template` | No | Send an email using an existing template. Resolves placeholders (e.g. `{{card.title}}`). `card_id`, `email_template_id` required; optional `to`, `from_` to override defaults. |

## Webhook tools

| Tool | Read-only | Role |
|------|-----------|------|
| `create_webhook` | No | Register a webhook for pipe events; `url` must be HTTPS; `actions` is a list of event names (e.g. `['card.move', 'card.create']`). Use `introspect_type('WebhookActions')` for valid actions. |
| `delete_webhook` | No | Permanently delete a webhook by ID (`destructiveHint=True` — confirm with the user first). |
