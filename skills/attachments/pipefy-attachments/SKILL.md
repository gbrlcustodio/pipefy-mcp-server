---
name: pipefy-attachments
description: >
  Use this skill when the user wants to upload a file to a Pipefy card or
  table-record attachment field. Covers both the local-file path and the
  in-memory bytes (base64) input modes through the MCP tools and the CLI.
tags: [pipefy, attachments, upload, card, table-record]
---

# Attachments

Upload one file at a time to a card or table-record attachment field. The
upload goes through Pipefy's presigned URL flow (request URL, S3 PUT, then
field update). **2 MCP tools, 1 CLI command.**

---

## When to use

- The user says "attach this file to card X" or "upload to the documents field
  on record Y".
- The user has a file on their local filesystem (a path like `~/report.pdf`
  or `/tmp/export.csv`) or in-memory bytes the agent itself generated.

Do not use this skill for:

- Reading or listing existing attachments. There is no list/download tool in
  this skill scope. Cards and table records expose their attachments through
  the regular card/record fetch tools.
- Bulk uploads. One file per call; iterate at the agent layer.

## Prerequisites

- A Pipefy `organization_id`. Find it via `get_organization` or `get_pipe`.
- A target `card_id` or `table_record_id`.
- The attachment field's slug (the human-readable id like `document_upload`,
  not the field's uuid). Find it on the card or table record fetch tools.
- The file itself, either:
  - At a path the MCP server can read (it runs locally as the user, so any
    path the user can access is fine), or
  - As base64-encoded bytes if the agent has them in memory and never wrote
    to disk.

## Tools needed

| Tool (MCP) | CLI equivalent | Read-only |
|------------|----------------|-----------|
| `upload_attachment_to_card` | `pipefy attachment upload --card <id>` | No |
| `upload_attachment_to_table_record` | `pipefy attachment upload --record <id>` | No |

## Trust model

The MCP server runs locally as a subprocess of the agent runtime, with the
same filesystem access the user already has. There is no separate sandbox.
Any path the user can read is a valid `file_path`. There is no `file_url`
input mode in this distribution; if the agent has a URL, fetch it locally
first (e.g. `curl -o /tmp/file.pdf <url>`) and pass the resulting path.

## Steps

### Upload a local file to a card

Prefer `file_path` for anything on disk. `file_name` is inferred from the
path's basename when omitted, so callers usually only pass the four IDs and
the path.

MCP:

```
upload_attachment_to_card organization_id=42 card_id=1234 field_id=document_upload file_path=~/report.pdf
```

CLI:

```bash
pipefy attachment upload --org 42 --card 1234 --field document_upload --file ~/report.pdf
```

### Upload a local file to a table record

MCP:

```
upload_attachment_to_table_record organization_id=42 table_record_id=tr-555 field_id=document_upload file_path=/tmp/export.csv
```

CLI:

```bash
pipefy attachment upload --org 42 --record tr-555 --field document_upload --file /tmp/export.csv
```

### Upload in-memory bytes (no file on disk)

Use `file_content_base64` only when the agent generated the bytes itself and
never wrote them to disk (e.g. a synthesized PDF). Base64 inflates the
payload by ~33% over the MCP transport, so prefer `file_path` whenever the
file already exists on disk.

`file_name` is required in this mode (there is no path to infer from).

MCP:

```
upload_attachment_to_card organization_id=42 card_id=1234 field_id=document_upload file_name=invoice.pdf file_content_base64=JVBERi0xLjQK...
```

## Overriding the file name

When you want the attachment stored in Pipefy under a different name than the
local file's basename, pass `file_name` explicitly. It wins over the path's
basename.

```
upload_attachment_to_card ... file_path=/tmp/abc123.pdf file_name=Invoice-2026.pdf
```

## Success criteria

The tool returns a payload with `success: true`, a `download_url` (the signed
URL Pipefy returns), the inferred or explicit `content_type`, and the
`file_size` in bytes. The attachment field on the card or record now lists
the uploaded file.

## Failure modes

Each failure payload carries a `step` field. The possible values:

- **`step=validation`.** Both `file_path` and `file_content_base64` provided, neither provided, or `file_name` missing with base64 source. Recovery: provide exactly one source, plus a file name when using base64.
- **`step=file_read`.** `file_path` does not exist, points to a directory, is unreadable, or is **larger than 100 MiB**; or the base64 string is malformed or decodes to more than 100 MiB. Recovery: verify the path exists as a regular file the running user can read and is under the cap. For base64, check padding and that the alphabet is standard.
- **`step=presigned_url`.** Organization id rejected, field id not an attachment, or Pipefy refused the request. Recovery: confirm `organization_id` with `get_organization` and that the field is actually an attachment field on the target card or record.
- **`step=s3_upload`.** The presigned URL expired before PUT, or content/headers did not match what was signed. Recovery: retry the tool to obtain a fresh presigned URL. For unusually large files, expect Pipefy's storage policy to enforce the cap.
- **`step=field_update`.** The field rejected the new attachment list (wrong type, missing permission). Recovery: confirm the field accepts attachments and that the caller has write access to the card or record.

## See also

- `skills/pipes-and-cards/pipefy-pipes-and-cards/SKILL.md` — finding card ids and attachment field slugs.
- `skills/database-tables/pipefy-database-tables/SKILL.md` — finding table record ids and field slugs.
