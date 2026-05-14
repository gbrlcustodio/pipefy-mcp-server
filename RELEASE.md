# Release process

Workspace distributions (`pipefy-sdk`, `pipefy-mcp-server`, `pipefy-cli`) share a single **lockstep** version string in each package’s `__init__.py`. CI fails if those values diverge.

## Pre-launch (v0.x): GitHub Release only

PyPI publishing is **disabled** for tags that do not start with `v1.`. Pre-release installs use git references (for example `uvx --from git+https://github.com/<owner>/<repo>.git@vX.Y.Z --refresh pipefy-cli`).

1. Merge work to `main` and ensure `CHANGELOG.md` has everything under `## [Unreleased]`.
2. Bump the shared version (updates all three `__init__.py` files):

   ```bash
   uv run python scripts/bump_version.py patch
   ```

   Supported arguments: `major`, `minor`, `patch`, `prerelease`, or `version=X.Y.Z` (optional `v` prefix on `X.Y.Z`).

3. In `CHANGELOG.md`, replace the `## [Unreleased]` heading with `## [X.Y.Z] - YYYY-MM-DD` matching the new version and date (the Release workflow uses this section as the GitHub Release notes body).
4. Commit:

   ```bash
   git add -A && git commit -m "chore: release vX.Y.Z"
   ```

5. Tag and push:

   ```bash
   git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z
   ```

6. Wait for the **Release** workflow (`.github/workflows/release.yml`) to finish.
7. Confirm the GitHub Release lists the built wheels (`pipefy_cli-*.whl`, `pipefy_mcp_server-*.whl`, and `pipefy_sdk-*.whl` when produced). Optionally verify install from the tag, for example:

   ```bash
   uvx --from git+https://github.com/<owner>/<repo>.git@vX.Y.Z --refresh pipefy-cli --version
   ```

## v1.0 and later: GitHub Release + PyPI

Same steps as above. For tags whose name starts with **`v1.`** (for example `v1.0.0` or `v1.0.0rc1`), the release workflow also runs **Trusted Publishing** to upload the **`pipefy-cli`** and **`pipefy-mcp-server`** wheels to PyPI via `pypa/gh-action-pypi-publish` (the `pipefy-sdk` wheel is built for the GitHub Release but is **not** uploaded to PyPI until task 12.3 / ADR decides otherwise).

**Repository setup (maintainers):**

- Configure [Trusted Publishers](https://docs.pypi.org/trusted-publishers/using-a-publisher/) on PyPI for **`pipefy-cli`** and **`pipefy-mcp-server`** (and `pipefy-sdk` later if you enable it in the workflow).
- No long-lived PyPI token is required when using OIDC; the workflow requests `id-token: write`.

**After a v1.x tag:**

1. Confirm the new versions appear on PyPI for each published package.
2. Smoke-test a clean install, for example:

    ```bash
    uv tool install pipefy-cli
    ```

## Automation reference

| Piece | Role |
| --- | --- |
| `scripts/bump_version.py` | Reads the SDK `__version__`, applies the bump, writes the same value to SDK, MCP, and CLI `__init__.py`. |
| `.github/workflows/ci.yml` | Asserts the three `__version__` strings match. |
| `.github/workflows/release.yml` | On `v*` tags: asserts the tag matches SDK `__version__`, extracts the matching `CHANGELOG.md` section as the GitHub Release body, builds wheels and sdists with `uv build --all-packages -o dist --wheel --sdist`, attaches wheels to the GitHub Release, and publishes CLI + MCP wheels to PyPI only when `github.ref_name` starts with `v1.`. |
