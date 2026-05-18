---
name: pipefy-members-email-webhooks
description: >
  Use this skill when the user wants to manage pipe membership, send or read
  card inbox emails, use email templates, or manage webhooks. Covers 11 MCP tools.
tags: [pipefy, members, email, webhooks, inbox]
---

# Members, Email & Webhooks

Manage pipe membership, send emails from card inboxes, read inbox replies, and manage webhooks. **11 MCP tools.**

---

## Member management

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_pipe_members` | `pipefy member list --pipe <id>` | Yes | List all members of a pipe. |
| `invite_members` | `pipefy member invite` | No | Invite one or more users by email + role. |
| `remove_member_from_pipe` | `pipefy member remove` | No | **Two-step destructive.** Warns on external emails. |
| `set_role` | `pipefy member set-role` | No | Change a member's pipe role. |

### Steps — invite members

1. **Check existing members:**

   MCP: `get_pipe_members pipe_id=67890`

   CLI: `pipefy member list --pipe 67890`

2. **Invite new members:**

   MCP: `invite_members pipe_id=67890 members='[{"email":"alice@example.com","role_name":"member"},{"email":"bob@example.com","role_name":"admin"}]'`

   CLI: `pipefy member invite --pipe 67890 --email alice@example.com --role member`

   > Before inviting **external emails** (domain different from the org's known domains), warn the user that this is an external invitation and confirm before proceeding.

   > Before granting **admin role**, confirm with the user — admin is the highest pipe-level role.

---

## Email (card inbox)

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_card_inbox_emails` | `pipefy email inbox list --card <id>` | Yes | Read emails in a card's inbox. |
| `send_inbox_email` | `pipefy email inbox send` | No | Send an email from a card inbox. |
| `get_email_templates` | `pipefy email template list --repo <id>` | Yes | List org-level email templates. |
| `send_email_with_template` | `pipefy email template send` | No | Send using a template (substitutes variables). |

### Steps — send a card inbox email

1. **Get the card's inbox emails** (see what has been received):

   MCP: `get_card_inbox_emails card_id=12345`

2. **Send a reply:**

   MCP: `send_inbox_email card_id=12345 to="customer@example.com" subject="Your request is in progress" body="Hi, we are processing your request."`

   CLI: `pipefy email inbox send --card 12345 --to customer@example.com --subject "Your request is in progress" --body "Hi, we are processing your request." --from-email you@example.com`

---

## Webhooks

| Tool (MCP) | CLI | Read-only | Purpose |
|------------|-----|-----------|---------|
| `get_webhooks` | `pipefy webhook list --pipe <id>` | Yes | List all webhooks for a pipe. |
| `create_webhook` | `pipefy webhook create` | No | Register a new webhook endpoint. |
| `update_webhook` | `pipefy webhook update <id>` | No | Change URL, headers, or events. |
| `delete_webhook` | `pipefy webhook delete <id>` | No | **Two-step destructive.** |

### Steps — create a webhook

1. **List existing webhooks:**

   MCP: `get_webhooks pipe_id=67890`

   CLI: `pipefy webhook list --pipe 67890`

2. **Create the webhook:**

   MCP: `create_webhook pipe_id=67890 url="https://your-server.com/pipefy" actions='["card.create","card.done"]'`

   CLI: `pipefy webhook create --pipe 67890 --url https://your-server.com/pipefy --events card.create,card.done`

---

## Success criteria

- Invited members appear in `get_pipe_members`.
- Sent emails show in the card's inbox thread.
- Created webhooks receive test payloads from Pipefy on the configured events.

## Failure modes

- **`invite_members` fails with "user not found":** verify the email address is correct.
- **`send_inbox_email` fails:** the card must have an inbox enabled in the pipe settings.
- **Webhook never fires:** verify the pipe events match the configured `actions` list; check that the endpoint URL is publicly reachable (not localhost).
- **`delete_webhook` first call returns preview:** expected — show preview, then call with `confirm=true`.

## See also

- `skills/pipes-and-cards/` — create the pipe and cards before managing membership.
- `skills/observability/` — monitor email and webhook delivery logs.
