# LLM providers

Read-only discovery of the LLM providers an organization can use: custom (BYOM) providers, Pipefy-managed system providers, vendor model lists, owner defaults, provider dependencies, and a read-access probe. **5 tools.**

These are the discovery counterpart to the `providerId` / `systemProviderId` fields on AI agent behaviors (see [Automations & AI](automations-and-ai.md)): use `get_llm_providers` to find the IDs a behavior accepts.

---

| Tool | Read-only | Role |
|------|-----------|------|
| `get_llm_providers` | Yes | Lists custom and system providers in one union, paginated (`first` default 50, `after`) with `only_active` (filters custom providers only). Each node carries `type` (`byom` = custom, `system` = Pipefy-managed) plus `configuration`. |
| `get_available_ai_models` | Yes | Lists the model names a provider vendor exposes. `provider_name` is one of `openai`, `azure_openai`, `amazon_bedrock`, `custom`, `google_vertex_ai`, `oracle_oci`, `anthropic` (the API validates membership). |
| `get_default_llm_provider` | Yes | Resolves the default provider for an owner: `owner_type` is `organization` (default), `assistant`, or `behavior`. The returned `type` says whether the default is custom or system. |
| `get_llm_provider_dependencies` | Yes | Lists the owners (`ownerId` / `ownerType`) that depend on a provider — the blockers to check before deactivating or removing one. Paginated, with `total_count`. |
| `validate_llm_provider_access` | Yes | Probes whether the current credential can read the organization's providers, classifying failures into structured problems (permission denied / not found / invalid arguments) instead of opaque errors. |

## Identifiers: UUID vs numeric ID

The organization identifier is **not uniform** across these queries — this follows the Pipefy GraphQL API, not a toolkit choice:

- `get_llm_providers` and `get_llm_provider_dependencies` take the organization **UUID** (`organization_uuid`).
- `get_default_llm_provider` with `owner_type="organization"` takes the **numeric organization ID** as `owner_id`.
- `get_available_ai_models` takes no organization argument at all (vendor-level lookup).

`get_organization` returns both `id` and `uuid`, so one call resolves whichever form a tool needs.

## Configuration redaction

Provider `configuration` is included in read output, and the API **redacts secret values server-side**: placeholder markers come back instead of secrets (e.g. an access token reads as a redaction placeholder). Reading configuration never exposes credentials.

## Probe semantics

- A green `validate_llm_provider_access` proves **read access only** — never write entitlement. Provider mutations may still be denied.
- An **empty system-provider list** can mean Pipefy-managed system models are not enabled for the organization, rather than a permission problem. The probe reports `system_providers_visible` / `custom_providers_visible` separately and says so in its `note`.
- Permissions are asymmetric across the read surface: the provider **list** needs a weaker permission than the models / default / dependencies reads, so a green probe does not guarantee those three succeed for the same credential.
- The scoping of the stronger permission also differs: `get_available_ai_models` and `get_default_llm_provider` authorize against the **credential's own organization context**, while `get_llm_provider_dependencies` authorizes against the **target organization** passed as `organization_uuid` — the same token can be denied on the former and green on the latter.
- Probing an **unknown organization UUID** surfaces as permission denied rather than not-found (the API does not reveal whether the organization exists).

## Error classification

Failures on this surface are classified by a shared SDK-level module (`pipefy_sdk.graphql_problem`) into structured problems — `permission_denied`, `not_found`, `invalid_arguments`, `feature_not_enabled`, or `runtime` — carried on `error.details.kind` alongside the GraphQL `extensions.code` and `correlation_id`. The same classifier backs the CLI (`pipefy ai-provider ...`), so both surfaces report the same problem kinds.
