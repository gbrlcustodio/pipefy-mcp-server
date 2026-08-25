# Release process

Workspace distributions (`pipefy`, `pipefy-mcp-server`, `pipefy-cli`, `pipefy-auth`, `pipefy-infra`) share a single **lockstep** version string in each package's `__init__.py`. CI fails if those values diverge.

## Cutting a release

The Release workflow publishes to PyPI on **every `v*` tag**: it builds and uploads all five workspace wheels via Trusted Publishing, whatever the version. A pre-release tag (`aN` / `bN` / `rcN`, or the dashed `-alpha.N` / `-beta.N` forms) uploads to PyPI as a pre-release; a plain `uv` / `pip` install resolves it only while no stable version exists, otherwise pass `--pre` or pin the exact pre-release. A stable `vX.Y.Z` tag is what a plain install resolves by default.

## Which branch a tag comes from: alpha vs. beta

The branch a release is cut from determines its pre-release track, and `release.py` derives one from the other so a tag cannot be cut from the wrong branch:

| Track | Cut from | Purpose |
| --- | --- | --- |
| **alpha** (`vX.Y.Z-alpha.N`) | `dev` | Staging. Published to PyPI so the hosted MCP server's deployment wrapper can pin an exact version and exercise the release in staging. |
| **beta** (`vX.Y.Z-beta.N`) | `main` | The release. What the public `install.sh` resolves. |

One caveat on PyPI: `--pre` (and `uv`'s `--prerelease allow`) considers **every** pre-release and takes the highest version, so once `0.5.0-alpha.1` is published it outranks `0.4.0-beta.2` and a `--pre` install resolves the alpha. `install.sh` is unaffected — it filters alphas out by tag — but pin the exact version if you need the beta from PyPI.

This rule is enforced in three places, so a tag cannot be published from the wrong branch by mistake: `release.py` derives the required branch from the version and refuses a mismatch before it bumps; it re-checks the checked-out branch again immediately before cutting the tag (the bump commit lands in between); and the Release workflow itself asserts the tagged commit is an ancestor of `origin/dev` for an alpha, or `origin/main` for anything else. The last one is the one that matters — it runs before any wheel is built or uploaded, so even a tag pushed by hand from the wrong branch fails instead of publishing.

An alpha and the beta it becomes **share a core `X.Y.Z`**: `0.5.0-alpha.1` → `0.5.0-alpha.2` → promoted to `0.5.0-beta.1` on `main`. PEP 440 orders `0.5.0a1 < 0.5.0a2 < 0.5.0b1`, so each step is an upgrade. A new cycle opens the next core version (`0.6.0-alpha.1`).

Because the alpha line must sort **above** whatever `main` last released, an alpha always opens a core version `main` has not reached — you cannot cut `0.4.0-alpha.1` once `0.4.0-beta.2` is out, since `0.4.0a1 < 0.4.0b2`. `alpha-pr` refuses that, and refuses to run at all while `dev` is behind `main`, since `dev`'s `## [Unreleased]` would then still hold notes `main` has already released.

### Cutting an alpha from `dev`

A repository ruleset requires a pull request on **both** `main` and `dev`, so an alpha reaches its branch exactly the way a beta does. `alpha-pr` is `release-pr` based on `dev`:

```bash
uv run python scripts/release.py alpha-pr version=0.5.0-alpha.1   # opens a new alpha line
uv run python scripts/release.py alpha-pr prerelease              # next alpha in the current line
```

That branches off `origin/dev` as `rc-dev/release/vX.Y.Z-alpha.N`, bumps the version, pushes, and opens a PR into `dev`. After it merges, tag from `dev`:

```bash
git checkout dev && git pull
uv run python scripts/release.py publish
```

`publish` derives the branch from the version's own track, so the same command serves both lines — an alpha publishes from `dev`, a beta or stable from `main`, with no flag to get wrong. It builds and smoke-installs the wheels, tags, pushes **only the tag** (tags are unrestricted; the branch already carries the commit via the merged PR), watches the Release workflow, and verifies, asking for one confirmation before the irreversible push. If the release PR has not merged yet, it says so instead of attempting a push the ruleset would reject.

**An alpha does not stamp `CHANGELOG.md`.** `## [Unreleased]` stays put and keeps accumulating across `alpha.1..alpha.N`; the Release workflow uses that section as an alpha's GitHub Release body. This is what lets the eventual beta promotion stamp the whole set into one `## [X.Y.Z-beta.1]` section instead of finding the notes already spent on an alpha heading.

**An alpha never becomes what the public installer hands out.** Its GitHub Release is flagged as a pre-release, and `install.sh` resolves the newest release whose tag is *not* an alpha — so `curl … | sh` stays on the beta line. `release.py` asserts this after publishing an alpha (the inverse of the check it runs for a beta), so a leak fails the release rather than shipping quietly. Install an alpha on purpose with `install.sh --version vX.Y.Z-alpha.N`.

### Promoting an alpha to a beta

Once the alpha checks out in staging, promote it from `dev` with the `beta` bump, which keeps `X.Y.Z` and resets the counter (`0.5.0-alpha.3` → `0.5.0-beta.1`):

```bash
uv run python scripts/release.py release-pr beta
```

That opens the usual `dev → main` release PR; after it merges, `publish` from `main` cuts the tag (same command as the alpha line — the version decides the branch). `beta` only promotes an alpha — use `prerelease` to walk an existing beta line (`beta.1 → beta.2`) and `version=X.Y.Z` for anything else.

### Public beta line (`v0.2.0-beta.*`)

The next **GitHub pre-release** after the standalone repo’s [`v0.1.0-beta.1`](https://github.com/pipefy/ai-toolkit/releases/tag/v0.1.0-beta.1) is the **`v0.2.0-beta.*`** series on this monorepo (first cut: **`v0.2.0-beta.1`** unless you intentionally reuse another suffix). Same mechanics as any other tag: wheels attach to the GitHub Release and upload to PyPI as a pre-release (installable with `--pre`).

The Release workflow requires the git tag (without leading `v`) to **exactly match** `__version__` in `packages/sdk/src/pipefy_sdk/__init__.py` (and the MCP/CLI/Auth/Infra copies). For example tag **`v0.2.0-beta.1`** implies **`__version__ = "0.2.0-beta.1"`** in all five packages before you push the tag (set via step 2 below using `version=0.2.0-beta.1`, or edit the five `__init__.py` files together).

`scripts/release.py` drives the flow, split at the irreversible boundary — everything before the tag push is local and reversible, so you review before anything leaves your machine, the built wheels included. The subcommands are `release-pr` (open a dev→main release PR), `alpha-pr` (open a staging-alpha PR into `dev`), `prepare` (bump/commit locally), `publish` (build and smoke-install the wheels, tag the merged commit, push the tag, watch, verify), and `verify` (re-run the post-publish checks).

### Recommended: `dev → main` release PR

Most releases start from `dev`. `release.py release-pr <bump>` branches off the latest `origin/dev`, runs the same bump-and-stamp as `prepare`, pushes, and opens a PR into `main`:

```bash
uv run python scripts/release.py release-pr patch
```

It reads the current version and `## [Unreleased]` from `origin/dev` (not your checked-out branch), confirms the computed target, then opens the PR. After the PR is approved and merged into `main`, cut the release from `main` with `publish` (step 4 below) — deliberately a human step, so the tag push triggers the Release workflow. `release-pr` never tags or publishes.

**Precondition: `origin/dev` must contain every commit on `origin/main`.** Because the cut branches off `dev` and the released notes come from `dev`'s `## [Unreleased]` alone, anything merged straight into `main` — a doc fix, a CI workflow — would be stamped out of the release notes. `release-pr` refuses with the count and the remedy before it creates or pushes anything, so a stale `dev` costs nothing to walk away from: back-merge `main` into `dev`, then re-run. `alpha-pr` enforces the same precondition, since a staging cut that is missing what `main` already shipped does not represent what will ship. In the ordinary case the back-merge pull request is already open and waiting — see [Keeping `dev` and `main` reconciled](#keeping-dev-and-main-reconciled).

**A red DCO check on the release pull request is expected, and does not block it.** The cut carries every commit `dev` has that `main` does not, so it carries any commit whose author no longer matches its own `Signed-off-by` — a mismatch a squash merge introduces, and one nothing can repair once the commit is on a protected branch. See [Keeping `dev` and `main` reconciled](#keeping-dev-and-main-reconciled) for how it arises. No ruleset requires the check. Read it as history rather than as a fault in the release commit: a cut whose DCO is green because it carries almost nothing is a cut from the wrong place, and the notes it stamps will be missing what `dev` holds.

### The bump, step by step

`release-pr` automates steps 1–2 below off `dev`; they are spelled out here because the bump argument and its guards are what you actually choose. Note that `main` and `dev` both require a pull request, so a locally-prepared commit can never be pushed to either — `prepare` gives you the commit, but it still reaches the branch through a PR.

1. Ensure `CHANGELOG.md` has everything under `## [Unreleased]`.
2. Prepare the release. This bumps the shared version across every version-bearing file (via `scripts/bump_version.py`), stamps the `## [Unreleased]` CHANGELOG heading with the new version and today's date, re-seeds an empty `## [Unreleased]`, and commits — all locally:

   ```bash
   uv run python scripts/release.py prepare patch
   ```

   The bump argument accepts `major`, `minor`, `patch`, `prerelease`, `beta`, or `version=X.Y.Z` (optional `v` prefix on `X.Y.Z`). `prepare` prints the computed target (`Will bump 0.3.0-beta.1 -> 0.3.0-beta.2 and cut tag v0.3.0-beta.2. Proceed?`) and waits for confirmation before touching any file, so a wrong bump costs nothing to walk away from (`--yes` skips the prompt for automation). Note `prerelease` only increments the current pre-release track (`beta.1 -> beta.2`) and never promotes across tracks; `beta` is the one promotion (`alpha.N -> beta.1`, same `X.Y.Z`). For any other exact string pass `version=X.Y.Z` with the PEP-440 form (for example `version=0.5.0-beta.1`) so it matches `GITHUB_REF_NAME` without the leading `v`. `prepare` and `release-pr` both refuse an alpha-shaped target — alphas go through `alpha-pr`, the only flow that leaves `## [Unreleased]` unstamped.

3. Review the release commit (`git show HEAD`). Nothing has been pushed yet. **The diff is only half of what ships**, and the other half — do the wheels this commit produces actually install and start? — cannot be read off any diff, because a release breaks with nothing in the repository changing: a dependency published upstream inside the declared bounds is enough. So `publish` builds the wheels and installs them into a throwaway virtualenv before its confirmation prompt, putting the artifact review on the same reversible side of the boundary as the commit review.
4. Publish, from the branch the version ships from, once the release PR has merged. This builds and smoke-installs the wheels, tags `vX.Y.Z`, pushes **the tag only**, waits for the **Release** workflow (`.github/workflows/release.yml`), then verifies the result:

   ```bash
   uv run python scripts/release.py publish
   ```

   `publish` first refuses unless the checked-out branch matches the version's track and is in sync with its remote, so a release PR that has not merged yet is reported as such rather than surfacing as a rejected branch push.

   It then runs the **artifact check**: `uv build --all-packages --wheel` into a temporary directory (never `dist/`, so a stale local build cannot be mistaken for this one), one wheel per published member asserted before anything is installed, `pip install` of those wheels into a clean virtualenv, and `smoke_entry_points.py` under that virtualenv's interpreter to launch every console entry point. It is the same sequence `release.yml` runs from the same script, moved to the side of the boundary where a failure costs nothing — so the operator reads the real error locally, with no tag, no GitHub Release, and no manual withdrawal.

   Only then does it ask for the one confirmation before the irreversible tag push (pass `--yes` to skip the prompt in automation). The prompt states that the built wheels install and launch, so what was checked is in front of you when you answer it.

   The check resolves third-party dependencies from PyPI rather than `uv.lock`, and will occasionally pick a newer permitted version than the lock pins — that divergence is what it exists to expose. It therefore needs the index: while PyPI is unreachable, a cut cannot be made.

   Once the workflow finishes it asserts, and fails loudly on any gap, that the GitHub Release ships all five wheels (`pipefy-*.whl`, `pipefy_mcp_server-*.whl`, `pipefy_cli-*.whl`, `pipefy_auth-*.whl`, `pipefy_infra-*.whl`), that the published version installs from PyPI (`uvx --from "pipefy-cli==<PEP 440>" pipefy --version`), and that the `install.sh` dry-run resolves the just-cut tag (`Resolved tag: vX.Y.Z`). Re-run those checks any time with `uv run python scripts/release.py verify vX.Y.Z`.

5. Submit or refresh the Cursor Marketplace listing from `main` after every tag that ships a change to `.cursor-plugin/plugin.json` or `.mcp.json`. The listing is not cut by any workflow: those files ship with the repository, and a human submits them at [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish). Cursor reviews every plugin by hand and re-reviews each update, so budget for a review round rather than treating the submission as instant.

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

## The scheduled packaging gate

`uv.lock` pins every dependency, so the test suite passes against known-good versions no matter what is published to PyPI. That is what a lock is for, and it means **no test in this repository observes a fresh install**. The packaging smoke install is what covers that band: it installs into a clean virtualenv with `pip` and launches every console entry point, resolving dependencies from the index rather than the lock.

That gate runs on every push and pull request (`ci.yml`), on a daily schedule (`packaging-smoke.yml`), and once more inside `release.py publish` before the tag exists — the last of which is what makes the break stoppable, since `release.py verify` installs from PyPI only after the tag is public. The schedule is what covers the window between merges: a dependency breakage published upstream arms itself with zero commits here, and without a timer it stays invisible until someone happens to open a PR — or until a release is attempted, which is how `mcp` 2.0.0 was found: at the last possible moment, with the tag already pushed.

The scheduled workflow runs two jobs, because they see different failures:

- **Wheels built from this checkout** — the same check `ci.yml` runs. An upstream release outside the declared bounds breaks this one, and would have broken the *next* release.
- **Wheels already on PyPI** — a plain `pip install` of all five distributions by name, the way a user installs them. This catches a broken or incomplete upload, and upstream breakage against the bounds of the release that has *already* shipped. No `--pre` flag: pip falls back to a pre-release when a requirement has no stable release, so this resolves the newest pre-1.0 wheel today and the stable one after 1.0, with no edit. Either way it is what a plain install gets.

A failure opens a GitHub issue labelled `packaging-smoke-failure`, or comments on the open one so a break that persists across days stays a single thread. Close the issue once a run is green; the next failure opens a fresh one.

Two limits worth knowing rather than being surprised by:

- **The timer only fires from the default branch.** GitHub reads `schedule` and `workflow_dispatch` from `main` alone, so those two triggers stay inert until the workflow is promoted. The path-filtered `pull_request` trigger is unaffected, which is what exercises the workflow on the pull request that changes it.
- **The gate proves process startup, not behaviour.** A dependency release that breaks behaviour without breaking imports passes it, and the suite would not see it either, since the suite runs against the lock. Closing that band means running some portion of the tests unlocked.

## Keeping `dev` and `main` reconciled

`release-pr` refuses to cut while `origin/main` carries commits absent from `origin/dev`. That guard turns a silent hazard into a hard failure, but only at the *next* release — the drift itself persists for however long passes before someone tries to cut one, and it is diagnosed by whoever happens to be cutting rather than by whoever caused it.

`.github/workflows/backmerge.yml` closes that window from the other side. On every push to `main`, daily, and on demand, it counts `origin/dev..origin/main`. When that is zero it closes any open tracking issue and stops. When it is not, it cuts `rc-dev/chore/back-merge-main-<short-sha>` from `origin/dev`, merges `origin/main` into it, and opens a pull request into `dev` — so the reconciliation is waiting for review instead of waiting to be remembered.

**Merge a back-merge pull request with a merge commit, never a squash or a rebase.** Both discard the second parent, so `dev` gains the *content* of `main`'s commits but never their *ancestry*. `git rev-list --count origin/dev..origin/main` does not move, `release-pr` stays blocked, and the workflow proposes the same back-merge again on its next run — the loop never converges. This is not hypothetical: #577 was squash-merged and left the count at 9 with every file already in place. The generated pull request body says so. If a merged pull request is ever found alongside surviving drift, the next run repairs it without being asked: it cuts `rc-dev/chore/back-merge-main-<short-sha>-ancestry` from `dev`, merges `main` with `-s ours`, and opens that as a pull request. The repair takes no files, because a squash applies every file and drops only the second parent, so `dev`'s tree is already current and ancestry is the sole thing missing — a plain merge there would duplicate text `dev` already carries, since git reads one paragraph on each side as two independent additions. Squashing the repair in turn leaves the count exactly where it was, and that is where the automation stops and records the loop rather than opening a third pull request for one `main` head.

The branch name is derived from the `main` head, which is what makes a re-run idempotent: the same drift always resolves to the same branch, so an existing branch or pull request is recognized and left alone rather than pushed over. That matters because the ruleset blocks non-fast-forward pushes, and rewriting a branch under an open pull request destroys the incremental diff a reviewer is working through. A *closed* back-merge pull request is neither reopened nor re-pushed, because closing one is a human decision — but the divergence it left behind is still real, so it is recorded on the tracking issue instead of being treated as handled. Going quiet there is the exact failure this replaces: #564 and #565 were both closed without merging, and the drift then sat unnoticed for days.

**A conflict is a normal outcome, not a failure.** Release drift conflicts on `CHANGELOG.md` by construction, since `main` carries the stamped `## [X.Y.Z]` heading while `dev` still has those entries under `## [Unreleased]`; binary assets conflict whenever both branches touched one. Neither is resolvable automatically — `-X ours` and `-X theirs` both silently discard real work — so the workflow aborts the merge, pushes nothing, and opens an issue labelled `back-merge` naming the conflicting paths and the commands to resolve them. The run still exits zero: a red X on every release would train people to ignore it.

That exit code is conditional on the issue actually landing. Exiting zero is defensible only while the tracking issue is the compensating signal, so if the issue write also fails the run turns red — a green run with no pull request *and* no issue would be the silent drift this exists to end.

The issue is a single thread, found by its label rather than its title, and its title carries the live count. It closes on its own once the branches are back in sync, and also when a later `main` head produces a pull request that answers it, so conflict guidance never outlives the pull request that resolved it. A re-run that would say exactly the same thing stays silent, so an unresolved divergence does not accumulate one comment per morning.

Three things to know rather than be surprised by:

- **CI on the back-merge pull request depends on the `BACKMERGE_TOKEN` secret.** GitHub deliberately does not trigger `on: pull_request` workflows for a pull request opened with `GITHUB_TOKEN`, so without that secret the pull request carries no checks and its body says so plainly rather than merely *looking* green. The workflow reads `secrets.BACKMERGE_TOKEN || secrets.GITHUB_TOKEN`, so setting the secret turns checks on with no change to the workflow. It also lifts the separate repository setting that forbids Actions from creating pull requests at all. Use a GitHub App token or a fine-grained PAT scoped to this repository with `contents: write`, `pull-requests: write`, and `issues: write`. A classic PAT is the wrong instrument here — it is user-scoped, carries access to every repository its owner can reach, and does not expire.
- **Every real trigger resolves from `main`.** GitHub reads `schedule` and `workflow_dispatch` from the default branch alone, and reads `push` from the pushed commit itself, so all three require `.github/workflows/backmerge.yml` to exist on `main`. A copy that lives only on `dev` never runs. The two copies are kept byte-identical for the same reason, so a back-merge is a no-op on these paths rather than a conflict inside the script that performs it. The path-filtered `pull_request` trigger is unaffected, and runs in a dry run — every real step executes, but each push, pull request, and issue write is announced instead of performed, so editing this workflow cannot open a genuine back-merge off the branch under review.

- **A red DCO check on a back-merge is expected when its range carries such a commit, and does not block it.** A squash merge rewrites the author to the merging account's GitHub profile identity while the `Signed-off-by` trailer, being message text, is carried verbatim. A contributor whose git `user.name` differs from their GitHub display name therefore lands a commit whose author no longer matches its own sign-off, even though it passed DCO on its own pull request. That commit cannot be rewritten once it is on `main` or `dev`, so `dco-check` fails on every back-merge that carries it. A back-merge that follows a release carries the release commits alone and is green: the mismatched commits are already on `dev`, which is the opposite range from the cut that carried them there. The generated pull request body names the offending commits so the failure does not read as a new problem, and no ruleset requires the check.

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
| `scripts/release.py` | Guided release CLI. `release-pr <bump>` branches off `origin/dev`, bumps, stamps the `CHANGELOG.md` `## [Unreleased]` heading, and opens a release PR into `main`; `alpha-pr <bump>` is the same flow based on `dev`, which is what makes it skip the stamp. `prepare <bump>` runs `bump_version.py` and commits locally. `publish` builds the wheels and installs them into a throwaway virtualenv, then tags the merged release commit, pushes only the tag, watches the Release workflow, and verifies. That artifact check sits inside the shared irreversible half, after the repository-state guards and before the confirmation prompt: a wrong checkout or a colliding tag still fails in a second rather than after a build, and no flow can reach a tag push without crossing it. It builds into a temporary directory rather than `dist/` and runs `smoke_entry_points.py`, so it is the same check the workflows run, on the side of the boundary where a failure costs nothing; the confirmation prompt reports that the built wheels install and launch. `release_branch_for` derives the branch from the version's own pre-release track, so every flow refuses a target that ships from somewhere else, and `publish` needs no flag. No flow pushes a release branch — a ruleset requires a pull request on `main` and `dev` — so `publish` asserts the branch matches its remote instead. `verify <tag>` re-runs the post-publish checks (all five wheels on the GitHub Release, PyPI install resolves, and `install.sh` resolves the tag — or, for an alpha, provably does *not*). It shells out to `bump_version.py` for the transform rather than reimplementing it. |
| `scripts/bump_version.py` | Reads the SDK `__version__`, applies the bump (`major`/`minor`/`patch`/`prerelease`/`beta`, or an exact `version=`; `beta` promotes an alpha to the first beta of the same `X.Y.Z`), writes the same value to SDK, MCP, CLI, Auth, and Infra `__init__.py`, the root `pyproject.toml`'s `[project].version`, the `.claude-plugin/plugin.json` `version`, the `.claude-plugin/marketplace.json` catalog `version` (what the plugin marketplace UI shows), the `.cursor-plugin/plugin.json` `version`, the `.cursor-plugin/marketplace.json` catalog `version`, and each published package's sibling `==` pins, then runs `uv lock` to refresh `uv.lock`. Also exposes a `verify` mode that asserts every version-bearing file agrees, and `prerelease_track`, which classifies a version as alpha/beta/rc regardless of spelling — what `release.py` keys the branch gate off. |
| `install.sh` | Resolves the newest GitHub Release whose tag is **not** an alpha, so a staging alpha published off `dev` never becomes what a default `curl … \| sh` installs. Filters by tag shape rather than the API's `prerelease` flag, because the whole pre-1.0 line is betas that must stay installable. `--version <tag>` still installs any tag, alphas included. |
| `.github/workflows/ci.yml` | Invokes `scripts/bump_version.py verify` to assert that all version-bearing files match: the five `__version__` strings, the root `pyproject.toml` `[project].version`, `uv.lock`, the `.claude-plugin/plugin.json` `version`, the `.claude-plugin/marketplace.json` catalog `version`, the `.cursor-plugin/plugin.json` `version`, the `.cursor-plugin/marketplace.json` catalog `version`, and the sibling `==` pins in each published package's `pyproject.toml`. Also runs the packaging smoke install on every push and pull request. This and `packaging-smoke.yml` resolve dependencies from PyPI rather than `uv.lock`, as do the release workflow's smoke install and the artifact check `release.py publish` runs before the tag. |
| `.github/workflows/release.yml` | On `v*` tags, in two bands — everything validates, then everything publishes. **Validate:** asserts the tagged commit is on the branch its track ships from (`origin/dev` for an alpha, `origin/main` otherwise) before building anything, asserts the tag matches SDK `__version__`, extracts the matching `CHANGELOG.md` section as the GitHub Release body (for an alpha tag, which carries no stamped heading, falls back to `## [Unreleased]`), builds wheels and sdists with `uv build --all-packages -o dist --wheel --sdist`, guards with `smoke_entry_points.py --check-wheels dist` that `dist/` holds exactly one wheel per published member so a sixth member cannot ship unnoticed, copies those wheels to `dist-pypi/` (wheels only — PyPI does not get the sdists), then installs that set into a clean virtualenv and launches every console entry point. **Publish:** attaches the wheels to the GitHub Release, flagging alpha tags as GitHub pre-releases so the "Latest" badge stays on the newest beta, then uploads all five wheels to PyPI via Trusted Publishing. No step that publishes anything runs before the smoke install, so a validation failure leaves nothing behind but the tag — unavoidable, since the tag is what triggers the workflow — and a red run. PyPI goes last within the publish band, because an upload cannot be taken back while a GitHub Release can be deleted, which leaves one narrower gap by choice: a failing upload leaves a Release with no matching PyPI artifacts. A comment in the file marks the boundary, so the order is not reshuffled by someone tidying step layout. |
| `.github/workflows/packaging-smoke.yml` | Daily, and on demand: builds the wheels from the checkout and installs them into a clean virtualenv, and separately installs the five distributions already on PyPI by name, launching every console entry point in both. Covers the window between merges, where an upstream dependency release breaks a fresh install with no commit here to trigger anything. A failure opens or comments on an issue labelled `packaging-smoke-failure`. Inert until the file reaches `main`, since GitHub reads `schedule` from the default branch only. See [The scheduled packaging gate](#the-scheduled-packaging-gate). |
| `.github/workflows/backmerge.yml` | On every push to `main`, daily, and on demand: counts `origin/dev..origin/main` and, when it is non-zero, cuts `rc-dev/chore/back-merge-main-<short-sha>` from `origin/dev`, merges `origin/main` into it, and opens a pull request into `dev`. The branch name is derived from the `main` head, so a re-run recognizes an existing branch or pull request instead of pushing over it — the ruleset blocks non-fast-forward pushes, and rewriting a branch under review destroys the reviewer's incremental diff. A conflicting merge pushes nothing and opens or updates an issue labelled `back-merge` with the conflicting paths and the resolution commands; that issue closes on its own once the branches are back in sync, or when a later pull request answers it. A closed back-merge pull request is not reopened, but its unresolved drift is recorded rather than treated as handled. Exits zero when either a pull request or the tracking issue landed, and non-zero when neither did — a red run on every release trains people to ignore the signal, but a green run that surfaced nothing is worse. A back-merge that was squashed or rebased is detected on the next run — its pull request is merged while the divergence still stands — and answered with an `-s ours` ancestry repair, which records `main` as a parent and takes no files because the squash already delivered them. The decision logic lives in `.github/workflows/scripts/backmerge.py` and is unit-tested in `tests/test_backmerge.py`. Every real trigger resolves the file from `main`, so the copy there is kept byte-identical to `dev`'s. See [Keeping `dev` and `main` reconciled](#keeping-dev-and-main-reconciled). |
| `scripts/smoke_entry_points.py` | Both halves of the packaging smoke, shared by `ci.yml`, `release.yml`, and `packaging-smoke.yml`, and by `release.py publish`, so "every published member" and "every published entry point" each have one definition — including the wheel set `release.py verify` requires on the GitHub Release, derived from the same member list through `wheel_stem`. `--check-wheels <dir>` runs **before** the install and asserts the directory holds exactly one wheel per member — an incomplete set must not reach `pip`, which would satisfy the absent member from the index through the sibling `==` pins and smoke-test a wheel the build never produced. With no arguments it runs under the smoke virtualenv's interpreter and reads *installed* distribution metadata: it fails if a member is missing from the install, if a wheel stopped shipping its console script, or if any script's `--help` exits non-zero or hangs. Every discovered script is launched, so a newly added entry point is covered with no edit; `REQUIRED_SCRIPTS` is the floor that catches a lost one, and `tests/test_smoke_entry_points.py` asserts both constants still match the workspace's `pyproject.toml` files. |
