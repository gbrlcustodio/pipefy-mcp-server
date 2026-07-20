# Release process

Workspace distributions (`pipefy`, `pipefy-mcp-server`, `pipefy-cli`, `pipefy-auth`, `pipefy-infra`) share a single **lockstep** version string in each package's `__init__.py`. CI fails if those values diverge.

## Cutting a release

The Release workflow publishes to PyPI on **every `v*` tag**: it builds and uploads all five workspace wheels via Trusted Publishing, whatever the version. A pre-release tag (`aN` / `bN` / `rcN`, or the dashed `-alpha.N` / `-beta.N` forms) uploads to PyPI as a pre-release; a plain `uv` / `pip` install resolves it only while no stable version exists, otherwise pass `--pre` or pin the exact pre-release. A stable `vX.Y.Z` tag is what a plain install resolves by default.

### Public beta line (`v0.2.0-beta.*`)

The next **GitHub pre-release** after the standalone repo’s [`v0.1.0-beta.1`](https://github.com/pipefy/ai-toolkit/releases/tag/v0.1.0-beta.1) is the **`v0.2.0-beta.*`** series on this monorepo (first cut: **`v0.2.0-beta.1`** unless you intentionally reuse another suffix). Same mechanics as any other tag: wheels attach to the GitHub Release and upload to PyPI as a pre-release (installable with `--pre`).

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

6. Wait for the **Release** workflow (`.github/workflows/release.yml`) to finish.
7. Confirm the GitHub Release lists the built wheels (`pipefy_cli-*.whl`, `pipefy_mcp_server-*.whl`, `pipefy-*.whl`, `pipefy_auth-*.whl`, and `pipefy_infra-*.whl`). Optionally verify the published version installs from PyPI (use the PEP 440 form, e.g. `0.2.0b1`, not the `v0.2.0-beta.1` git tag):

   ```bash
   uvx --from "pipefy-cli==0.2.0b1" pipefy --version
   ```

   Sanity-check that the curl installer on `main` resolves the just-cut tag (no per-release maintenance needed; it hits the GitHub API at runtime):

   ```bash
   curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh \
     | sh -s -- --yes --no-skills --client none --dry-run
   ```

   Output should include `Resolved tag: vX.Y.Z` (right after `Resolving latest release from GitHub...`).

## Verification (cross-platform smoke test)

After tagging a release, run the following on macOS and a Linux machine (or CI runner) to confirm the wheels install correctly. Pin the **PyPI/PEP 440** version (e.g. `0.2.0b1`), which differs from the `v0.2.0-beta.1` git tag:

```bash
# Install CLI from PyPI at the just-published version
uvx --from "pipefy-cli==0.2.0b1" pipefy --version
# Expected: the published version

# Verify MCP server starts
uvx "pipefy-mcp-server==0.2.0b1" --help
# Expected: help text (server may block in stdio mode, Ctrl-C after banner)
```

## v1.0 and later: stable PyPI installs

Same steps as above. PyPI publishing already runs on every tag; a **`v1.`** tag with no pre-release suffix (for example `v1.0.0`) is simply what a plain `pip install` / `uv tool install` resolves without `--pre`. The workflow uploads all five workspace wheels to PyPI via `pypa/gh-action-pypi-publish` on every tag.

**Repository setup (maintainers):**

- Configure [Trusted Publishers](https://docs.pypi.org/trusted-publishers/using-a-publisher/) on PyPI for **all five** workspace distributions. Uploads fail until each project has a matching trusted publisher; use PyPI's pending-publisher flow for the first upload of a new name.
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
| `scripts/bump_version.py` | Reads the SDK `__version__`, applies the bump, writes the same value to SDK, MCP, CLI, Auth, and Infra `__init__.py`, the root `pyproject.toml`'s `[project].version`, the `.claude-plugin/plugin.json` `version`, and each published package's sibling `==` pins, then runs `uv lock` to refresh `uv.lock`. Also exposes a `verify` mode that asserts every version-bearing file agrees. |
| `.github/workflows/ci.yml` | Invokes `scripts/bump_version.py verify` to assert that all version-bearing files match: the five `__version__` strings, the root `pyproject.toml` `[project].version`, `uv.lock`, the `.claude-plugin/plugin.json` `version`, and the sibling `==` pins in each published package's `pyproject.toml`. |
| `.github/workflows/release.yml` | On `v*` tags: asserts the tag matches SDK `__version__`, extracts the matching `CHANGELOG.md` section as the GitHub Release body, builds wheels and sdists with `uv build --all-packages -o dist --wheel --sdist`, guards that `dist/` holds exactly five wheels (one per workspace member) so a sixth member cannot ship unnoticed, attaches wheels to the GitHub Release, and uploads all five wheels to PyPI via Trusted Publishing on every `v*` tag. |
