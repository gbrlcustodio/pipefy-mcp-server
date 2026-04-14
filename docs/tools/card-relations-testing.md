# Card relations: manual test scenario (`get_card_relations` / `delete_card_relation`)

Use this flow to **prepare data in Pipefy** so `get_card_relations` returns non-empty
`child_relations` / `parent_relations`, and to smoke-test the MCP tools against a real
workspace.

## What the GraphQL API exposes

- On type `Card`, the public schema uses **snake_case** fields: `child_relations` and
  `parent_relations` (each is `[CardRelationship]`). The MCP query matches this.
- **`createCardRelation`** exists on the public API (link two cards using a **pipe
  relation** as `source_id`).
- **`deleteCardRelation`** is **not** listed in the standard public mutation list from
  live introspection (only `createCardRelation` is guaranteed). The MCP still exposes
  `delete_card_relation` for environments that add the mutation; against the default
  public API you may get a GraphQL error when `confirm=True`. Prefer verifying the
  **read** path first.

## Preconditions

1. **Two pipes** in the same organization (or a parent/child pipe setup you already use).
2. A **pipe relation** between them: use `get_pipe_relations` on the parent pipe and
   note a relation **`id`** — that value is the **`source_id`** for `create_card_relation`
   (same as in the Pipefy UI: connection between pipes).
3. At least **two cards**: one card that will act as **parent** and one as **child** in
   the linked-pipes sense (each in the correct pipe per your relation config).

## Steps (happy path for `get_card_relations`)

1. **`get_pipe_relations(pipe_id=<parent_pipe_id>)`**  
   Pick one relation’s `id` → **`source_id`**.

2. **`get_cards` / `find_cards`** (or the UI) to obtain:
   - **`parent_id`**: card ID in the parent pipe.
   - **`child_id`**: card ID in the child pipe.

3. **`create_card_relation(parent_id=..., child_id=..., source_id=...)`**  
   Creates the card-to-card link through that pipe relation.

4. **`get_card_relations(card_id=<either_card_id>)`**  
   You should see at least one entry under **`child_relations`** or **`parent_relations`**
   (depending on direction), with `name`, `pipe { id name }`, and `cards { id title }`.

## Optional: destructive preview only

5. **`delete_card_relation(child_id=..., parent_id=..., source_id=..., confirm=False)`**  
   Confirms the two-step guard (preview payload). Only set **`confirm=True`** if your
   tenant exposes a working delete mutation and you intend to remove the link.

## Quick reference IDs (example)

Replace with your real IDs from `search_pipes` / `get_pipe` / `get_cards`:

| Role        | Typical source                          |
|------------|------------------------------------------|
| `pipe_id`  | Pipe where you list relations or cards   |
| `source_id`| `get_pipe_relations` → relation `id`     |
| `parent_id`| Card on the parent side of the relation  |
| `child_id` | Card on the child side of the relation   |

## Troubleshooting

- **Empty lists** after linking: confirm the pipe relation direction and that both cards
  sit in the pipes expected by that relation.
- **`delete_card_relation` GraphQL error**: expected on some APIs; rely on
  `create_card_relation` + `get_card_relations` for core validation.
