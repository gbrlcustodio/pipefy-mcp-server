# Release process

Workspace distributions (`pipefy`, `pipefy-mcp-server`, `pipefy-cli`, `pipefy-auth`, `pipefy-infra`) share a single **lockstep** version string in each package's `__init__.py`. CI fails if those values diverge.

## Cutting a release

The Release workflow publishes to PyPI on **every `v*` tag**: it builds and uploads all five workspace wheels via Trusted Publishing, whatever the version. A pre-release tag (`aN` / `bN` / `rcN`, or the dashed `-alpha.N` / `-beta.N` forms) uploads to PyPI as a pre-release; a plain `uv` / `pip` install resolves it only while no stable version exists, otherwise pass `--pre` or pin the exact pre-release. A stable `vX.Y.Z` tag is what a plain install resolves by default.

## Which branch a tag comes from: alpha vs. beta

The branch a release is cut from determines its pre-release track, and `release.py` derives one from the other so a tag cannot be cut from the wrong branch:

| Track | Cut from | Purpose |
| --- | --- | --- |
| **alpha** (`vX.Y.Z-alpha.N`) | `dev` | Staging. Published to PyPI so the hosted MCP server's deployment wrapper can pin an exact version and exercise the release in staging. |
| **beta** (`vX.Y.Z-beta.N`) | `main` | The release. What the public installer and a default `--pre` install resolve. |

This rule is enforced in three places, so a tag cannot be published from the wrong branch by mistake: `release.py` derives the required branch from the version and refuses a mismatch before it bumps; it re-checks the checked-out branch again immediately before cutting the tag (the bump commit lands in between); and the Release workflow itself asserts the tagged commit is an ancestor of `origin/dev` for an alpha, or `origin/main` for anything else. The last one is the one that matters — it runs before any wheel is built or uploaded, so even a tag pushed by hand from the wrong branch fails instead of publishing.

An alpha and the beta it becomes **share a core `X.Y.Z`**: `0.5.0-alpha.1` → `0.5.0-alpha.2` → promoted to `0.5.0-beta.1` on `main`. PEP 440 orders `0.5.0a1 < 0.5.0a2 < 0.5.0b1`, so each step is an upgrade. A new cycle opens the next core version (`0.6.0-alpha.1`).

Because the alpha line must sort **above** whatever `main` last released, an alpha always opens a core version `main` has not reached — you cannot cut `0.4.0-alpha.1` once `0.4.0-beta.2` is out, since `0.4.0a1 < 0.4.0b2`. `release.py alpha` refuses that, and refuses to run at all while `dev` is behind `main`, since `dev`'s `## [Unreleased]` would then still hold notes `main` has already released.

### Cutting an alpha from `dev`

```bash
git checkout dev && git pull
uv run python scripts/release.py alpha version=0.5.0-alpha.1   # opens a new alpha line
uv run python scripts/release.py alpha prerelease              # next alpha in the current line
```

Unlike the beta flow there is no release PR — `dev` is already the integration branch, so the bump commit and the tag land on it directly. `alpha` bumps, commits, tags, pushes, watches the Release workflow, and verifies, asking for one confirmation before the irreversible push.

**An alpha does not stamp `CHANGELOG.md`.** `## [Unreleased]` stays put and keeps accumulating across `alpha.1..alpha.N`; the Release workflow uses that section as an alpha's GitHub Release body. This is what lets the eventual beta promotion stamp the whole set into one `## [X.Y.Z-beta.1]` section instead of finding the notes already spent on an alpha heading.

**An alpha never becomes what the public installer hands out.** Its GitHub Release is flagged as a pre-release, and `install.sh` resolves the newest release whose tag is *not* an alpha — so `curl … | sh` stays on the beta line. `release.py` asserts this after publishing an alpha (the inverse of the check it runs for a beta), so a leak fails the release rather than shipping quietly. Install an alpha on purpose with `install.sh --version vX.Y.Z-alpha.N`.

### Promoting an alpha to a beta

Once the alpha checks out in staging, promote it from `dev` with the `beta` bump, which keeps `X.Y.Z` and resets the counter (`0.5.0-alpha.3` → `0.5.0-beta.1`):

```bash
uv run python scripts/release.py release-pr beta
```

That opens the usual `dev → main` release PR; after it merges, `publish` from `main` cuts the tag. `beta` only promotes an alpha — use `prerelease` to walk an existing beta line (`beta.1 → beta.2`) and `version=X.Y.Z` for anything else.

### Public beta line (`v0.2.0-beta.*`)

The next **GitHub pre-release** after the standalone repo’s [`v0.1.0-beta.1`](https://github.com/pipefy/ai-toolkit/releases/tag/v0.1.0-beta.1) is the **`v0.2.0-beta.*`** series on this monorepo (first cut: **`v0.2.0-beta.1`** unless you intentionally reuse another suffix). Same mechanics as any other tag: wheels attach to the GitHub Release and upload to PyPI as a pre-release (installable with `--pre`).

The Release workflow requires the git tag (without leading `v`) to **exactly match** `__version__` in `packages/sdk/src/pipefy_sdk/__init__.py` (and the MCP/CLI/Auth/Infra copies). For example tag **`v0.2.0-beta.1`** implies **`__version__ = "0.2.0-beta.1"`** in all five packages before you push the tag (set via step 2 below using `version=0.2.0-beta.1`, or edit the five `__init__.py` files together).

`scripts/release.py` drives the flow, split at the irreversible boundary — everything before the tag push is local and reversible, so you review before anything leaves your machine. The subcommands are `release-pr` (open a dev→main release PR), `prepare` (bump/stamp/commit on `main`), `publish` (tag, push, watch, verify), `alpha` (cut a staging alpha off `dev`), and `verify` (re-run the post-publish checks).

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

   The bump argument accepts `major`, `minor`, `patch`, `prerelease`, `beta`, or `version=X.Y.Z` (optional `v` prefix on `X.Y.Z`). `prepare` prints the computed target (`Will bump 0.3.0-beta.1 -> 0.3.0-beta.2 and cut tag v0.3.0-beta.2. Proceed?`) and waits for confirmation before touching any file, so a wrong bump costs nothing to walk away from (`--yes` skips the prompt for automation). Note `prerelease` only increments the current pre-release track (`beta.1 -> beta.2`) and never promotes across tracks; `beta` is the one promotion (`alpha.N -> beta.1`, same `X.Y.Z`). For any other exact string pass `version=X.Y.Z` with the PEP-440 form (for example `version=0.5.0-alpha.1`) so it matches `GITHUB_REF_NAME` without the leading `v`.

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
| `scripts/release.py` | Guided release CLI. `release-pr <bump>` branches off `origin/dev`, prepares, and opens a release PR into `main`. `prepare <bump>` runs `bump_version.py`, stamps the `CHANGELOG.md` `## [Unreleased]` heading, and commits on `main` (all local, reversible). `publish` tags, pushes, watches the Release workflow, then verifies. `alpha <bump>` does the whole thing in one step on `dev` for a staging alpha — bump (no CHANGELOG stamp), commit, tag, push, watch, verify. `release_branch_for` derives the required branch from the version's own pre-release track, so `publish` refuses an alpha and `alpha` refuses a non-alpha. `verify <tag>` re-runs the post-publish checks (all five wheels on the GitHub Release, PyPI install resolves, and `install.sh` resolves the tag — or, for an alpha, provably does *not*). It shells out to `bump_version.py` for the transform rather than reimplementing it. |
| `scripts/bump_version.py` | Reads the SDK `__version__`, applies the bump (`major`/`minor`/`patch`/`prerelease`/`beta`, or an exact `version=`; `beta` promotes an alpha to the first beta of the same `X.Y.Z`), writes the same value to SDK, MCP, CLI, Auth, and Infra `__init__.py`, the root `pyproject.toml`'s `[project].version`, the `.claude-plugin/plugin.json` `version`, the `.claude-plugin/marketplace.json` catalog `version` (what the plugin marketplace UI shows), and each published package's sibling `==` pins, then runs `uv lock` to refresh `uv.lock`. Also exposes a `verify` mode that asserts every version-bearing file agrees, and `prerelease_track`, which classifies a version as alpha/beta/rc regardless of spelling — what `release.py` keys the branch gate off. |
| `install.sh` | Resolves the newest GitHub Release whose tag is **not** an alpha, so a staging alpha published off `dev` never becomes what a default `curl … \| sh` installs. Filters by tag shape rather than the API's `prerelease` flag, because the whole pre-1.0 line is betas that must stay installable. `--version <tag>` still installs any tag, alphas included. |
| `.github/workflows/ci.yml` | Invokes `scripts/bump_version.py verify` to assert that all version-bearing files match: the five `__version__` strings, the root `pyproject.toml` `[project].version`, `uv.lock`, the `.claude-plugin/plugin.json` `version`, the `.claude-plugin/marketplace.json` catalog `version`, and the sibling `==` pins in each published package's `pyproject.toml`. |
| `.github/workflows/release.yml` | On `v*` tags: asserts the tagged commit is on the branch its track ships from (`origin/dev` for an alpha, `origin/main` otherwise) before building anything, asserts the tag matches SDK `__version__`, extracts the matching `CHANGELOG.md` section as the GitHub Release body (for an alpha tag, which carries no stamped heading, falls back to `## [Unreleased]`), builds wheels and sdists with `uv build --all-packages -o dist --wheel --sdist`, guards that `dist/` holds exactly five wheels (one per workspace member) so a sixth member cannot ship unnoticed, attaches wheels to the GitHub Release, flags alpha tags as GitHub pre-releases so the "Latest" badge stays on the newest beta, and uploads all five wheels to PyPI via Trusted Publishing on every `v*` tag. |
