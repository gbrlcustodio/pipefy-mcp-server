# Release process

Workspace distributions (`pipefy-sdk`, `pipefy-mcp-server`, `pipefy-cli`, `pipefy-auth`, `pipefy-infra`) share a single **lockstep** version string in each package's `__init__.py`. CI fails if those values diverge.

## Pre-launch (v0.x): GitHub Release only

PyPI publishing is **disabled** for tags that do not start with `v1.`. Pre-release installs use git references (for example `uvx --from git+https://github.com/<owner>/<repo>.git@vX.Y.Z --refresh pipefy-cli`).

### Public beta line (`v0.2.0-beta.*`)

The next **GitHub pre-release** after the standalone repo’s [`v0.1.0-beta.1`](https://github.com/gbrlcustodio/pipefy-mcp-server/releases/tag/v0.1.0-beta.1) is the **`v0.2.0-beta.*`** series on this monorepo (first cut: **`v0.2.0-beta.1`** unless you intentionally reuse another suffix). Same mechanics as any other **v0.x** tag: attach wheels to the GitHub Release; **no PyPI** until **`v1.`**.

The Release workflow requires the git tag (without leading `v`) to **exactly match** `__version__` in `packages/sdk/src/pipefy_sdk/__init__.py` (and the MCP/CLI/Auth/Infra copies). For example tag **`v0.2.0-beta.1`** implies **`__version__ = "0.2.0-beta.1"`** in all five packages before you push the tag (set via step 2 below using `version=0.2.0-beta.1`, or edit the five `__init__.py` files together).

1. Merge work to `main` and ensure `CHANGELOG.md` has everything under `## [Unreleased]`.
2. Bump the shared version (updates all five `__init__.py` files):

   ```bash
   uv run python scripts/bump_version.py patch
   ```

   Supported arguments: `major`, `minor`, `patch`, `prerelease`, or `version=X.Y.Z` (optional `v` prefix on `X.Y.Z`).

   For a **`v0.2.0-beta.*`** Git tag, pass the exact PEP-440 string (for example `version=0.2.0-beta.1`) so it matches `GITHUB_REF_NAME` without the leading `v`.

3. In `CHANGELOG.md`, replace the `## [Unreleased]` heading with `## [X.Y.Z] - YYYY-MM-DD` matching the new version and date (the Release workflow uses this section as the GitHub Release notes body).
4. Commit:

   ```bash
   git add -A && git commit -m "chore: release vX.Y.Z"
   ```

5. Tag and push:

   ```bash
   git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z
   ```

6. Roll the `latest` moving tag to point at the same commit. The README install snippets and shipping `.mcp.json` pin `@latest`, so this is what makes new installs pick up the release:

   ```bash
   git tag -f latest vX.Y.Z && git push --force-with-lease origin latest
   ```

7. Wait for the **Release** workflow (`.github/workflows/release.yml`) to finish.
8. Confirm the GitHub Release lists the built wheels (`pipefy_cli-*.whl`, `pipefy_mcp_server-*.whl`, `pipefy_sdk-*.whl`, `pipefy_auth-*.whl`, and `pipefy_infra-*.whl`). Optionally verify install from the tag, for example:

   ```bash
   uvx --from git+https://github.com/<owner>/<repo>.git@vX.Y.Z --refresh pipefy-cli --version
   ```

   Sanity-check that the curl installer on `main` resolves the just-cut tag (no per-release maintenance needed; it hits the GitHub API at runtime):

   ```bash
   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh \
     | sh -s -- --yes --no-skills --client none --dry-run
   ```

   Output should include `Resolved tag: vX.Y.Z` (right after `Resolving latest release from GitHub...`).

## Verification (cross-platform smoke test)

After tagging a release, run the following on macOS and a Linux machine (or CI runner) to confirm the wheels install correctly:

```bash
# Install CLI from the tagged release
uvx --from "git+https://github.com/<owner>/pipefy-labs.git@vX.Y.Z" --refresh pipefy-cli --version
# Expected: X.Y.Z

# Verify MCP server starts
uvx --from "git+https://github.com/<owner>/pipefy-labs.git@vX.Y.Z" --refresh pipefy-mcp-server --help
# Expected: help text (server may block in stdio mode — Ctrl-C after banner)
```

## v1.0 and later: GitHub Release + PyPI

Same steps as above. For tags whose name starts with **`v1.`** (for example `v1.0.0` or `v1.0.0rc1`), the release workflow also runs **Trusted Publishing** to upload the **`pipefy-cli`** and **`pipefy-mcp-server`** wheels to PyPI via `pypa/gh-action-pypi-publish` (the `pipefy-sdk` wheel is built for the GitHub Release but is **not** uploaded to PyPI until maintainers enable it in the workflow; see **Repository setup** below).

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
| `scripts/bump_version.py` | Reads the SDK `__version__`, applies the bump, writes the same value to SDK, MCP, CLI, Auth, and Infra `__init__.py`. |
| `.github/workflows/ci.yml` | Asserts the five `__version__` strings match. |
| `.github/workflows/release.yml` | On `v*` tags: asserts the tag matches SDK `__version__`, extracts the matching `CHANGELOG.md` section as the GitHub Release body, builds wheels and sdists with `uv build --all-packages -o dist --wheel --sdist`, attaches wheels to the GitHub Release, and publishes CLI + MCP wheels to PyPI only when `github.ref_name` starts with `v1.`. |
