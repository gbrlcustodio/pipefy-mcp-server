# LLM providers

Discovery and management of the LLM providers an organization can use: custom (BYOM) providers, Pipefy-managed system providers, vendor model lists, owner defaults, provider dependencies, a read-access probe, plus custom-provider writes (create/update/delete, active-status toggle, and organization default set/reset). **11 tools.**

These are the counterpart to the `providerId` / `systemProviderId` fields on AI agent behaviors (see [Automations & AI](automations-and-ai.md)): use `get_llm_providers` to find the IDs a behavior accepts, and the write tools to manage the custom providers behind them.

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_llm_providers` | Yes | Lists custom and system providers in one union, paginated (`first` default 50, `after`) with `only_active` (filters custom providers only). Each node carries `type` (`byom` = custom, `system` = Pipefy-managed) plus `configuration` (secrets redacted). |
| `get_available_ai_models` | Yes | Lists the model names a provider vendor exposes. `provider_name` is one of `openai`, `azure_openai`, `amazon_bedrock`, `custom`, `google_vertex_ai`, `oracle_oci`, `anthropic` (the API validates membership). |
| `get_default_llm_provider` | Yes | Resolves the default provider for an owner: `owner_type` is `organization` (default), `assistant`, or `behavior`. The returned `type` says whether the default is custom or system. |
| `get_llm_provider_dependencies` | Yes | Lists the owners (`ownerId` / `ownerType`) that depend on a provider — the blockers to check before deactivating or removing one. Paginated, with `total_count`. |
| `validate_llm_provider_access` | Yes | Probes whether the current credential can read the organization's providers, classifying failures into structured problems (permission denied / not found / invalid arguments) instead of opaque errors. |
| `create_llm_provider` | No | Creates a custom (BYOM) provider. Configuration comes from a local JSON file (`configuration_file_path`), never inline; the created provider is returned without its configuration. |
| `update_llm_provider` | No | Updates a custom provider with a full replacement configuration (from a local JSON file). Redaction placeholders preserve stored secrets — see [The update flow](#the-update-flow). |
| `delete_llm_provider` | No | Deletes a custom provider permanently. Two-step `confirm`. Check dependencies first. |
| `set_llm_provider_active_status` | No | Activates or deactivates a custom provider (`active`). No organization argument — the org is resolved from the session. |
| `set_default_llm_provider` | No | Sets the organization's default provider. Exactly one of `provider_id` (custom) / `system_provider_id` (system). |
| `reset_default_llm_provider` | No | Clears the organization's default provider assignment. Reversible via `set_default_llm_provider`. |

## Permissions

- The **write** tools (create, update, delete, active-status, default set/reset) require the `manage_ai_providers` **organization** permission and an **eligible (billable) plan**. This is a stronger, distinct entitlement from `manage_ai_agents` (which governs pipe-scoped AI agents and knowledge bases).
- The **read** surface is weaker: the provider list needs only read access. So `validate_llm_provider_access` proving green does **not** imply the write entitlement — a write can still be denied.

### Owner-scoped operations need an organization-bound credential

`set_llm_provider_active_status`, `set_default_llm_provider`, `reset_default_llm_provider`, and the organization-owner read `get_default_llm_provider` authorize against the **organization context of the credential itself**, not an argument. A **service-account** credential is bound to one organization and supplies that context; a bare **personal access token** does not, so these operations return `permission_denied` with a personal token **regardless of the organization passed** — even when the same token can `create`/`update`/`delete` providers in that organization (those authorize against the passed `organization_uuid` instead). Run these owner-scoped tools with a service account bound to the target organization, and pass that organization's numeric id.

## Identifiers: UUID vs numeric ID

> Full cross-tool map: [identifiers.md](identifiers.md).

The organization identifier is **not uniform** across these tools — this follows the Pipefy GraphQL API, not a toolkit choice:

- `get_llm_providers`, `get_llm_provider_dependencies`, `create_llm_provider`, `update_llm_provider`, and `delete_llm_provider` take the organization **UUID** (`organization_uuid`).
- `get_default_llm_provider` (with `owner_type="organization"`), `set_default_llm_provider`, and `reset_default_llm_provider` take the **numeric organization ID** (`owner_id` / `organization_id`).
- `set_llm_provider_active_status` takes **no** organization argument — the org is resolved from the credential's session.
- `get_available_ai_models` takes no organization argument at all (vendor-level lookup).

`get_organization` returns both `id` and `uuid`, so one call resolves whichever form a tool needs.

## Configuration and secrets

Custom-provider configuration is secret-bearing (API keys, cloud credentials). The write tools handle it so secrets never leak:

- **File-path only.** `create_llm_provider` / `update_llm_provider` (and the CLI `--config-file`) accept configuration **only via a local JSON file path**, never as an inline argument. The secret therefore never appears in a tool-call argument, shell history, or argument log.
- **Never returned.** The create/update response omits `configuration` entirely — only non-secret identity/state fields (`id`, `name`, `type`, `active`, `organizationDefault`) come back.
- **Never echoed in errors.** A missing, oversized, or malformed configuration file fails with the file path and a structural reason only (never the file contents).
- **Redacted on read.** `get_llm_providers` / `get_default_llm_provider` return `configuration` with secret values replaced by the `__REDACTED__` placeholder server-side; reading configuration never exposes credentials.

The configuration is a JSON object whose `provider` key selects the vendor (`openai`, `anthropic`, `amazon-bedrock`, `azure-openai`, `google-vertex-ai`, `oracle-oci`, `custom`). The toolkit treats it as an opaque object: **vendor/model membership and credential validity are validated server-side**, including a live credential test call. So an invalid key, an unsupported model, or a vendor that can't do a requested capability surfaces as a backend rejection, not a client-side error. Use `get_available_ai_models` to discover valid model names for a vendor.

**Vendor strings are surface-specific and not interchangeable.** The `configuration.provider` key here uses hyphens (`amazon-bedrock`, `azure-openai`, `google-vertex-ai`, `oracle-oci`), while `get_available_ai_models` takes the same vendor as `provider_name` in snake_case (`amazon_bedrock`, `azure_openai`, `google_vertex_ai`, `oracle_oci`). Single-word vendors (`openai`, `anthropic`, `custom`) are identical on both. Do not copy a value from one surface into the other: a snake_case `configuration.provider` is rejected as an invalid adapter, and a hyphenated `provider_name` is rejected by the models lookup.

Example `configuration.json` (placeholders only — never commit real secrets):

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "auth": { "token": "sk-REPLACE_ME" }
}
```

## The update flow

`update_llm_provider` sends a **full replacement** configuration: the API requires a complete `configuration` object on every call, not a partial patch. The recommended flow keeps your provider definition editable without ever re-typing secrets:

1. Fetch the provider with `get_llm_providers`. Its `configuration` comes back with secret values shown as the `__REDACTED__` placeholder.
2. Copy that configuration into a local JSON file and edit the non-secret fields you want to change (e.g. `model`).
3. Run `update_llm_provider` with that file. **Any value left as `__REDACTED__` preserves the stored secret** — the server recognizes the placeholder and keeps the existing credential. You do not need to re-supply secrets to change other fields.
4. To **rotate** a secret, replace the placeholder with the new real value in the file before updating.

Keep your provider's configuration file as the client-side source of truth: because reads redact secrets, the toolkit cannot reconstruct the full plaintext configuration for you.

## Probe semantics and write-gating

- A green `validate_llm_provider_access` proves **read access only** — never the `manage_ai_providers` write entitlement. Provider mutations may still be denied.
- An **empty system-provider list** can mean Pipefy-managed system models are not enabled for the organization, rather than a permission problem. The probe reports `system_providers_visible` / `custom_providers_visible` separately and says so in its `note`.
- Permissions are asymmetric across the read surface: the provider **list** needs a weaker permission than the models / default / dependencies reads, so a green probe does not guarantee those three succeed for the same credential.
- The scoping of the stronger permission also differs: `get_available_ai_models` and `get_default_llm_provider` authorize against the **credential's own organization context**, while `get_llm_provider_dependencies` authorizes against the **target organization** passed as `organization_uuid` — the same token can be denied on the former and green on the latter.
- Probing an **unknown organization UUID** surfaces as permission denied rather than not-found (the API does not reveal whether the organization exists).
- **Clean-gate contract.** The probe can return a success that still carries a `problem` — when the API returns partial data alongside GraphQL errors, the probe surfaces the classified error rather than discarding it, and deliberately does not flip `ok`. Write-gating (the CLI runs the probe before create/update) therefore treats the gate as clean only when it is **`ok` and carries no `problem`**; a present `problem` is partial denial and is never read as full access.

## Defaults (organization-scoped)

`set_default_llm_provider` and `reset_default_llm_provider` operate on the **organization** owner (`organization_id` is the numeric org ID). Setting the default requires **exactly one** of `provider_id` (a custom/BYOM provider) or `system_provider_id` (a Pipefy-managed system provider); passing both or neither is rejected. Reset clears the assignment and is reversible by setting it again.

## Deletes and dependencies

`delete_llm_provider` is permanent and requires confirmation (MCP `confirm=True`; CLI prompts unless `--yes`). Before deleting or deactivating a provider, run `get_llm_provider_dependencies` — owners that still reference it are blockers.

## Configuration redaction

Provider `configuration` is included in read output, and the API **redacts secret values server-side**: `__REDACTED__` placeholders come back instead of secrets. Reading configuration never exposes credentials.

## Error classification

Failures on this surface are classified by a shared SDK-level module (`pipefy_sdk.graphql_problem`) into structured problems — `permission_denied`, `not_found`, `invalid_arguments`, `feature_not_enabled`, or `runtime` — carried on `error.details.kind` alongside the GraphQL `extensions.code` and `correlation_id`. The same classifier backs the CLI (`pipefy ai-provider ...`), so both surfaces report the same problem kinds.
