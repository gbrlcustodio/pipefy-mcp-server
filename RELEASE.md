# Release process

Workspace distributions (`pipefy`, `pipefy-mcp-server`, `pipefy-cli`, `pipefy-auth`, `pipefy-infra`) share a single **lockstep** version string in each package's `__init__.py`. CI fails if those values diverge.

## Cutting a release

The Release workflow publishes to PyPI on **every `v*` tag**: it builds and uploads all five workspace wheels via Trusted Publishing, whatever the version. A pre-release tag (`aN` / `bN` / `rcN`, or the dashed `-alpha.N` / `-beta.N` forms) uploads to PyPI as a pre-release; a plain `uv` / `pip` install resolves it only while no stable version exists, otherwise pass `--pre` or pin the exact pre-release. A stable `vX.Y.Z` tag is what a plain install resolves by default.

### Public beta line (`v0.2.0-beta.*`)

The next **GitHub pre-release** after the standalone repo’s [`v0.1.0-beta.1`](https://github.com/pipefy/ai-toolkit/releases/tag/v0.1.0-beta.1) is the **`v0.2.0-beta.*`** series on this monorepo (first cut: **`v0.2.0-beta.1`** unless you intentionally reuse another suffix). Same mechanics as any other tag: wheels attach to the GitHub Release and upload to PyPI as a pre-release (installable with `--pre`).

The Release workflow requires the git tag (without leading `v`) to **exactly match** `__version__` in `packages/sdk/src/pipefy_sdk/__init__.py` (and the MCP/CLI/Auth/Infra copies). For example tag **`v0.2.0-beta.1`** implies **`__version__ = "0.2.0-beta.1"`** in all five packages before you push the tag (set via step 2 below using `version=0.2.0-beta.1`, or edit the five `__init__.py` files together).

`scripts/release.py` drives the flow, split at the irreversible boundary — everything before the tag push is local and reversible, so you review before anything leaves your machine. The subcommands are `release-pr` (open a dev→main release PR), `prepare` (bump/stamp/commit on `main`), `publish` (tag, push, watch, verify), and `verify` (re-run the post-publish checks).

### Recommended: `dev → main` release PR

Most releases start from `dev`. `release.py release-pr <bump>` branches off the latest `origin/dev`, runs the same bump-and-stamp as `prepare`, pushes, and opens a PR into `main`:

```bash
uv run python scripts/release.py release-pr patch
```

It reads the current version and `## [Unreleased]` from `origin/dev` (not your checked-out branch), confirms the computed target, then opens the PR. After the PR is approved and merged into `main`, cut the release from `main` with `publish` (step 4 below) — deliberately a human step, so the tag push triggers the Release workflow. `release-pr` never tags or publishes.

### From `main` directly

If `main` already carries the merged work, run the steps below (this is also exactly what `release-pr` automates for steps 1–2, off `dev`).

1. Merge work to `main` and ensure `CHANGELOG.md` has everything under `## [Unreleased]`.
2. Prepare the release. This bumps the shared version across every version-bearing file (via `scripts/bump_version.py`), stamps the `## [Unreleased]` CHANGELOG heading with the new version and today's date, re-seeds an empty `## [Unreleased]`, and commits — all locally:

   ```bash
   uv run python scripts/release.py prepare patch
   ```

   The bump argument accepts `major`, `minor`, `patch`, `prerelease`, or `version=X.Y.Z` (optional `v` prefix on `X.Y.Z`). `prepare` prints the computed target (`Will bump 0.3.0-beta.1 -> 0.3.0-beta.2 and cut tag v0.3.0-beta.2. Proceed?`) and waits for confirmation before touching any file, so a wrong bump costs nothing to walk away from (`--yes` skips the prompt for automation). Note `prerelease` only increments the current pre-release track (`beta.1 -> beta.2`) and never promotes across tracks; to go `alpha.N -> beta.1`, or to a **`v0.2.0-beta.*`** tag, or to any exact string, pass `version=X.Y.Z` with the PEP-440 form (for example `version=0.2.0-beta.1`) so it matches `GITHUB_REF_NAME` without the leading `v`.

3. Review the release commit (`git show HEAD`). Nothing has been pushed yet.
4. Publish. This tags `vX.Y.Z`, pushes `main` and the tag, waits for the **Release** workflow (`.github/workflows/release.yml`), then verifies the result:

   ```bash
   uv run python scripts/release.py publish
   ```

   `publish` asks for one confirmation before the irreversible tag push (pass `--yes` to skip it in automation). Once the workflow finishes it asserts, and fails loudly on any gap, that the GitHub Release ships all five wheels (`pipefy-*.whl`, `pipefy_mcp_server-*.whl`, `pipefy_cli-*.whl`, `pipefy_auth-*.whl`, `pipefy_infra-*.whl`), that the published version installs from PyPI (`uvx --from "pipefy-cli==<PEP 440>" pipefy --version`), and that the `install.sh` dry-run resolves the just-cut tag (`Resolved tag: vX.Y.Z`). Re-run those checks any time with `uv run python scripts/release.py verify vX.Y.Z`.

## Verification (cross-platform smoke test)

`release.py publish` verifies on the machine it runs on. To confirm the wheels also install on the other platform, run the following on macOS and a Linux machine (or CI runner). Pin the **PyPI/PEP 440** version (e.g. `0.2.0b1`), which differs from the `v0.2.0-beta.1` git tag:

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
| `scripts/release.py` | Guided release CLI. `release-pr <bump>` branches off `origin/dev`, prepares, and opens a release PR into `main`. `prepare <bump>` runs `bump_version.py`, stamps the `CHANGELOG.md` `## [Unreleased]` heading, and commits on `main` (all local, reversible). `publish` tags, pushes, watches the Release workflow, then verifies. `verify <tag>` re-runs the post-publish checks (all five wheels on the GitHub Release, PyPI install resolves, `install.sh` dry-run resolves the tag). It shells out to `bump_version.py` for the transform rather than reimplementing it. |
| `scripts/bump_version.py` | Reads the SDK `__version__`, applies the bump, writes the same value to SDK, MCP, CLI, Auth, and Infra `__init__.py`, the root `pyproject.toml`'s `[project].version`, the `.claude-plugin/plugin.json` `version`, the `.claude-plugin/marketplace.json` catalog `version` (what the plugin marketplace UI shows), and each published package's sibling `==` pins, then runs `uv lock` to refresh `uv.lock`. Also exposes a `verify` mode that asserts every version-bearing file agrees. |
| `.github/workflows/ci.yml` | Invokes `scripts/bump_version.py verify` to assert that all version-bearing files match: the five `__version__` strings, the root `pyproject.toml` `[project].version`, `uv.lock`, the `.claude-plugin/plugin.json` `version`, the `.claude-plugin/marketplace.json` catalog `version`, and the sibling `==` pins in each published package's `pyproject.toml`. |
| `.github/workflows/release.yml` | On `v*` tags: asserts the tag matches SDK `__version__`, extracts the matching `CHANGELOG.md` section as the GitHub Release body, builds wheels and sdists with `uv build --all-packages -o dist --wheel --sdist`, guards that `dist/` holds exactly five wheels (one per workspace member) so a sixth member cannot ship unnoticed, attaches wheels to the GitHub Release, and uploads all five wheels to PyPI via Trusted Publishing on every `v*` tag. |
