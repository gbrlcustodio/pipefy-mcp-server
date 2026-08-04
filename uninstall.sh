#!/bin/sh
# uninstall.sh — report Pipefy toolkit state across every install channel and MCP client.
#
# This version scans only. It reads; it never removes, moves, or edits anything,
# and the single path it writes is a tempfile holding its own record stream.
#
# Channels: the Claude Code plugin, a local install (install.sh / uv tool /
# uvx), and the hosted HTTP server. Clients: Claude Code, Cursor, Claude
# Desktop, Codex.
#
# A registration is matched on what it *runs*, not on what it is called. The
# registration key is free text — a real environment had the server registered
# as `pipefy-dev` — so keying on the name misses exactly the entries that
# shadow a working one. Matching stays structural: an exact command name, an
# exact argument, an exact URL host, a JSON key path, a TOML section header, a
# keychain service attribute, an exact environment variable name. Never a
# substring search: "pipefy" turns up in unrelated hostnames, mail addresses
# and directory names, and `env | grep -i pipefy` matches PWD for anyone
# working inside a directory named after it.
#
# Exit codes: 0 nothing found, 1 findings present, 2 the scan itself failed.

set -eu

REPO="pipefy/ai-toolkit"
CANONICAL_NAME="pipefy"        # the name install.sh writes; the documented invariant
KEYCHAIN_SERVICE="pipefy"      # keyring service attribute
SERVER_BINARY="pipefy-mcp-server"
HOSTED_HOST="mcp.pipefy.com"   # the documented hosted endpoint, and the only one
RUNNERS="uvx uv npx python python3 pipx"
PLUGIN_ID="pipefy@pipefy"
MARKETPLACE_ID="pipefy"

CLIENT=""
ALLOW_ROOT=0
DRY_RUN=0

OS=""
CONFIG_DIR=""
PYTHON3=""
RECORDS=""
FINDINGS=0
SCAN_ERRORS=0
TAB=$(printf '\t')

# Secrets. `_session_masking_env_vars()` (packages/cli/.../commands/auth.py)
# inspects PIPEFY_TOKEN plus both sides of the legacy alias map in
# packages/auth/.../settings.py; the iPaaS client secret is added because this
# list answers "what is a secret", which is a wider question than that
# function's "what outranks a stored session". Pinned by
# tests/test_uninstall_scan.py.
CRED_ENV_NAMES="PIPEFY_TOKEN
PIPEFY_SERVICE_ACCOUNT_CLIENT_ID
PIPEFY_SERVICE_ACCOUNT_CLIENT_SECRET
PIPEFY_OAUTH_CLIENT
PIPEFY_OAUTH_SECRET
PIPEFY_IPAAS_OAUTH_CLIENT_SECRET"

# Non-credential configuration variables: every name in the docs/config.md
# tables plus every name the pydantic settings models read. Informational —
# they change behaviour rather than granting access. Pinned by the same test.
CONFIG_ENV_NAMES="PIPEFY_ALLOW_INSECURE_URLS
PIPEFY_AUTH_CLIENT_ID
PIPEFY_AUTH_URL
PIPEFY_BASE_URL
PIPEFY_CONFIG_FILE
PIPEFY_DEFAULT_WEBHOOK_NAME
PIPEFY_DISABLE_STORED_SESSION
PIPEFY_GQL_REUSE_FETCHED_GRAPHQL_SCHEMA
PIPEFY_IPAAS_OAUTH_CLIENT_ID
PIPEFY_IPAAS_OAUTH_REDIRECT_URI
PIPEFY_IPAAS_URL
PIPEFY_JWT_AUDIENCE
PIPEFY_JWT_ISSUER_URL
PIPEFY_JWT_JWKS_URI
PIPEFY_JWT_VERIFY_AUDIENCE
PIPEFY_KEYCHAIN_BACKEND
PIPEFY_MCP_ALLOWED_HOSTS
PIPEFY_MCP_ALLOWED_ORIGINS
PIPEFY_MCP_ALLOW_INSECURE_HTTP_BIND
PIPEFY_MCP_HOST
PIPEFY_MCP_LOG_LEVEL
PIPEFY_MCP_PORT
PIPEFY_MCP_PROFILE
PIPEFY_MCP_RS_REQUIRED_SCOPES
PIPEFY_MCP_RS_RESOURCE_SERVER_URL
PIPEFY_MCP_TOOLSETS
PIPEFY_MCP_TRANSPORT
PIPEFY_MCP_UNIFIED_ENVELOPE
PIPEFY_ORG_ID
PIPEFY_PERMISSION_DENIED_ENRICHMENT_TIMEOUT_SECONDS
PIPEFY_PORTAL_ORG_UUID"

say() { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
err() { printf 'error: %s\n' "$*" >&2; exit 2; }

section() { printf '\n== %s ==\n' "$*"; }
# A finding is state on this machine that a teardown would have to deal with.
finding() { printf '  * %s\n' "$*"; FINDINGS=$((FINDINGS + 1)); }
note() { printf '  - %s\n' "$*"; }
detail() { printf '      %s\n' "$*"; }
# A source this run could not inspect, so a partial scan never reads as clean.
uninspected() { printf '  ! %s\n' "$*"; SCAN_ERRORS=$((SCAN_ERRORS + 1)); }

print_help() {
    cat <<EOF
Usage: uninstall.sh [OPTIONS]

Report Pipefy toolkit state across every install channel and MCP client.
This version detects only; it removes nothing.

MCP registrations are matched on what they run — the $SERVER_BINARY
command, a known runner invoking it, or the hosted endpoint's host — so an
entry registered under any name is found.

Options:
  --scan              Report state and exit. The only mode this version has,
                      and what a bare invocation does.
  --client <id>       Accepted and validated for symmetry with install.sh.
                      One of: claude-code, claude-desktop, cursor, codex, none.
                      Detection always sweeps every client regardless, since
                      the point is finding state you forgot about.
  --dry-run           Accepted for symmetry with install.sh. A scan has no
                      side effects, so this changes nothing.
  --allow-root        Allow running as root (refuses by default).
  -h, --help          Show this help.

Exit codes:
  0  nothing found
  1  findings present
  2  the scan itself failed (a source could not be inspected)

Examples:
  curl -LsSf https://raw.githubusercontent.com/$REPO/main/uninstall.sh \\
    | sh -s -- --scan

  ./uninstall.sh --scan
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --scan) shift ;;
            --client) [ $# -ge 2 ] || err "--client requires a value"; CLIENT="$2"; shift 2 ;;
            --client=*) CLIENT="${1#--client=}"; shift ;;
            --dry-run) DRY_RUN=1; shift ;;
            --allow-root) ALLOW_ROOT=1; shift ;;
            -h|--help) print_help; exit 0 ;;
            *) err "Unknown flag: $1 (try --help)" ;;
        esac
    done
    case "$CLIENT" in
        ""|claude-code|claude-desktop|cursor|codex|none) ;;
        *) err "Invalid --client: $CLIENT (use claude-code|claude-desktop|cursor|codex|none)" ;;
    esac
}

refuse_root() {
    if [ "$(id -u)" = "0" ] && [ "$ALLOW_ROOT" -eq 0 ]; then
        err "Refusing to run as root. Re-run as a regular user, or pass --allow-root."
    fi
}

detect_platform() {
    OS="$(uname -s)"
    case "$OS" in
        Darwin|Linux) ;;
        *) err "Unsupported OS: $OS. uninstall.sh supports macOS and Linux." ;;
    esac
}

# Same resolution as pipefy_infra.config.config_dir(): XDG_CONFIG_HOME wins,
# ~/.config otherwise. PIPEFY_CONFIG_FILE relocates config.toml only, never the
# directory, which is why the file path is resolved separately.
resolve_config_dir() {
    if [ -n "${XDG_CONFIG_HOME:-}" ]; then
        CONFIG_DIR="$XDG_CONFIG_HOME/pipefy"
    else
        CONFIG_DIR="$HOME/.config/pipefy"
    fi
}

config_toml_path() {
    if [ -n "${PIPEFY_CONFIG_FILE:-}" ]; then
        printf '%s\n' "$PIPEFY_CONFIG_FILE"
    else
        printf '%s\n' "$CONFIG_DIR/config.toml"
    fi
}

# Follow a symlink chain by hand: `readlink -f` is not POSIX and is missing on
# older macOS. Bounded so a cycle cannot hang the scan.
resolve_link() {
    _rl_target="$1"
    _rl_hops=0
    while [ -L "$_rl_target" ] && [ "$_rl_hops" -lt 16 ]; do
        _rl_next=$(readlink "$_rl_target") || break
        case "$_rl_next" in
            /*) _rl_target="$_rl_next" ;;
            *) _rl_target="$(dirname "$_rl_target")/$_rl_next" ;;
        esac
        _rl_hops=$((_rl_hops + 1))
    done
    printf '%s\n' "$_rl_target"
}

path_dirs() {
    _old_ifs=$IFS
    IFS=:
    set -f
    # Splitting on ':' is the point here.
    # shellcheck disable=SC2086
    set -- $PATH
    set +f
    IFS=$_old_ifs
    for _pd in "$@"; do
        if [ -n "$_pd" ]; then
            printf '%s\n' "$_pd"
        else
            printf '%s\n' "."
        fi
    done
}

# Project scopes to inspect: the working tree this ran from, and every path in
# its `git worktree list`. The probe adds every project Claude Code knows.
project_dirs() {
    printf '%s\n' "$PWD"
    command -v git >/dev/null 2>&1 || return 0
    git rev-parse --show-toplevel >/dev/null 2>&1 || return 0
    git worktree list --porcelain 2>/dev/null \
        | awk '/^worktree /{ print substr($0, 10) }' || true
}

records() {
    awk -F'\t' -v want="$1" '$1 == want' "$RECORDS"
}

# The probe writes "-" where a field is empty; see its emit().
is_set() {
    [ -n "${1:-}" ] && [ "$1" != "-" ]
}

# Host of a URL, lowercased, with userinfo and port stripped. Compared for
# equality against the documented host, never searched for a substring.
url_host() {
    _uh="$1"
    case "$_uh" in *://*) _uh="${_uh#*://}" ;; esac
    _uh="${_uh%%/*}"
    _uh="${_uh%%\?*}"
    case "$_uh" in *@*) _uh="${_uh##*@}" ;; esac
    case "$_uh" in
        \[*) _uh="${_uh#\[}"; _uh="${_uh%%\]*}" ;;
        *) _uh="${_uh%%:*}" ;;
    esac
    printf '%s\n' "$_uh" | tr 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' 'abcdefghijklmnopqrstuvwxyz'
}

# A stdio entry runs our server when its command is the server binary, or a
# known runner with the server binary as an exact argument.
stdio_matches() {
    _sm_cmd="${1##*/}"
    shift
    [ "$_sm_cmd" = "$SERVER_BINARY" ] && return 0
    for _sm_runner in $RUNNERS; do
        [ "$_sm_cmd" = "$_sm_runner" ] || continue
        for _sm_arg in "$@"; do
            [ "$_sm_arg" = "$SERVER_BINARY" ] && return 0
        done
    done
    return 1
}

# ---------------------------------------------------------------- JSON probe

# Every JSON-backed source is read by this one python3 program. python3
# degrades per source: without it the JSON sources report "not inspected" and
# the run exits 2. Everything else here (PATH, keychain, config dir, uv cache,
# completions, skills, the Codex TOML, the environment) needs no python3.
run_json_probe() {
    [ -n "$PYTHON3" ] || return 1
    SCAN_ENV_CRED="$CRED_ENV_NAMES" \
    SCAN_ENV_CONFIG="$CONFIG_ENV_NAMES" \
    SCAN_CANONICAL_NAME="$CANONICAL_NAME" \
    SCAN_SERVER_BINARY="$SERVER_BINARY" \
    SCAN_HOSTED_HOST="$HOSTED_HOST" \
    SCAN_RUNNERS="$RUNNERS" \
    SCAN_PLUGIN_ID="$PLUGIN_ID" \
    SCAN_MARKETPLACE_ID="$MARKETPLACE_ID" \
    "$PYTHON3" - "$@" <<'PY' >>"$RECORDS"
import json
import os
import posixpath
import sys

HOME = os.path.expanduser("~")
CANON = os.environ["SCAN_CANONICAL_NAME"]
BINARY = os.environ["SCAN_SERVER_BINARY"]
HOSTED_HOST = os.environ["SCAN_HOSTED_HOST"]
RUNNERS = set(os.environ["SCAN_RUNNERS"].split())
PLUGIN = os.environ["SCAN_PLUGIN_ID"]
MARKET = os.environ["SCAN_MARKETPLACE_ID"]
CRED = set(os.environ["SCAN_ENV_CRED"].split())
CONFIG = set(os.environ["SCAN_ENV_CONFIG"].split())
PIPEFY_ENV = CRED | CONFIG


def emit(*fields):
    # "-" stands in for an empty field: tab is IFS whitespace, so `read` in the
    # consuming shell would otherwise collapse a run of tabs and shift columns.
    clean = []
    for field in fields:
        text = str(field).replace("\t", " ").replace("\n", " ")
        clean.append(text if text else "-")
    sys.stdout.write("\t".join(clean) + "\n")


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        emit("err", path, "unreadable: %s" % (exc.strerror or exc))
        return None
    if not text:
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        emit("err", path, "not valid JSON: %s" % exc)
        return None
    if not isinstance(data, dict):
        emit("err", path, "root is not a JSON object")
        return None
    return data


def url_host(url):
    """Host of a URL, lowercased, compared for equality — never searched."""
    text = str(url)
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0].split("?", 1)[0]
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    if text.startswith("["):
        text = text[1:].split("]", 1)[0]
    else:
        text = text.split(":", 1)[0]
    return text.lower()


def describe(entry):
    """(kind, endpoint, command, args) for one entry. Values are never read."""
    if not isinstance(entry, dict):
        return ("malformed", "<entry is not an object>", "", [])
    kind = entry.get("type")
    url = entry.get("url")
    command = entry.get("command")
    if kind in ("http", "streamable-http", "sse", "ws"):
        return (kind, str(url) if url else "<missing url>", "", [])
    if command is not None:
        raw = entry.get("args")
        args = [str(a) for a in raw] if isinstance(raw, list) else []
        return ("stdio", " ".join([str(command)] + args), str(command), args)
    if url is not None:
        # Claude Code reads a type-less entry as stdio, so it never starts.
        return ("malformed", "%s (url with no type)" % url, "", [])
    return ("malformed", "<neither command nor url>", "", [])


def classify(name, entry):
    """definite / possible / no, from what the entry runs rather than its name."""
    kind, endpoint, command, args = describe(entry)
    if kind == "stdio":
        if posixpath.basename(command) == BINARY:
            return kind, endpoint, command, "definite"
        if posixpath.basename(command) in RUNNERS and BINARY in args:
            return kind, endpoint, command, "definite"
    elif kind in ("http", "streamable-http", "sse", "ws"):
        if url_host(endpoint) == HOSTED_HOST:
            return kind, endpoint, command, "definite"
    # Weak signals only ever produce an unverified report, never a match: the
    # key name is free text and an env block is the user's own.
    named_for_us = name == CANON or name.startswith((CANON + "-", CANON + "_"))
    env = entry.get("env") if isinstance(entry, dict) else None
    tagged = isinstance(env, dict) and bool(set(env) & PIPEFY_ENV)
    if named_for_us or tagged:
        return kind, endpoint, command, "possible"
    return kind, endpoint, command, "no"


def scan_env_block(path, keypath, block):
    if not isinstance(block, dict):
        return
    for key in block:
        if key in CRED:
            emit("envkey", path, "%s.%s" % (keypath, key), key, "credential")
        elif key in CONFIG:
            emit("envkey", path, "%s.%s" % (keypath, key), key, "config")


MCP_ROWS = []


def walk_servers(path, keypath, servers, scope, projdir):
    if not isinstance(servers, dict):
        return
    for name, entry in servers.items():
        kind, endpoint, command, match = classify(name, entry)
        if match != "no":
            emit("mcp", match, name, scope, projdir, path, kind, endpoint, command)
            MCP_ROWS.append(
                (match, name, scope, projdir, path, kind, endpoint, command)
            )
        if isinstance(entry, dict):
            scan_env_block(path, "%s.%s.env" % (keypath, name), entry.get("env"))


def listed(value, name):
    return isinstance(value, list) and name in value


def scan_settings(path, projdir):
    data = load(path)
    if data is None:
        return
    scan_env_block(path, "env", data.get("env"))
    markets = data.get("extraKnownMarketplaces")
    if isinstance(markets, dict) and MARKET in markets:
        emit("marketplace", path, "extraKnownMarketplaces.%s" % MARKET, "")
    plugins = data.get("enabledPlugins")
    if isinstance(plugins, dict) and PLUGIN in plugins:
        emit("pluginflag", path, "enabledPlugins[%s]" % PLUGIN,
             "enabled" if plugins[PLUGIN] else "disabled")
    if listed(data.get("disabledMcpjsonServers"), CANON):
        emit("disabledjson", projdir, path)
    if listed(data.get("enabledMcpjsonServers"), CANON):
        emit("enabledjson", projdir, path)
    if listed(data.get("disabledMcpServers"), CANON):
        emit("disabledsrv", projdir, path)


project_dirs = []
for raw in sys.argv[1:]:
    if raw and raw not in project_dirs:
        project_dirs.append(raw)

# --- ~/.claude.json: user scope, local scope, per-project toggles, residue
claude_json = os.path.join(HOME, ".claude.json")
data = load(claude_json)
if data is not None:
    walk_servers(claude_json, "mcpServers", data.get("mcpServers"), "user", "-")
    usage = data.get("pluginUsage")
    if isinstance(usage, dict) and PLUGIN in usage:
        emit("pluginusage", claude_json, "pluginUsage[%s]" % PLUGIN)
    projects = data.get("projects")
    if isinstance(projects, dict):
        for pdir, pdata in projects.items():
            if pdir not in project_dirs:
                project_dirs.append(pdir)
            if not isinstance(pdata, dict):
                continue
            where = "%s projects.%s" % (claude_json, pdir)
            walk_servers(
                claude_json,
                "projects.%s.mcpServers" % pdir,
                pdata.get("mcpServers"),
                "local",
                pdir,
            )
            if listed(pdata.get("disabledMcpjsonServers"), CANON):
                emit("disabledjson", pdir, where)
            if listed(pdata.get("enabledMcpjsonServers"), CANON):
                emit("enabledjson", pdir, where)
            if listed(pdata.get("disabledMcpServers"), CANON):
                emit("disabledsrv", pdir, where)

# --- user settings files
for name in ("settings.json", "settings.local.json"):
    scan_settings(os.path.join(HOME, ".claude", name), "-")

# --- marketplace registry and installed plugins
known = os.path.join(HOME, ".claude", "plugins", "known_marketplaces.json")
data = load(known)
if isinstance(data, dict) and MARKET in data:
    entry = data[MARKET] if isinstance(data.get(MARKET), dict) else {}
    emit("marketplace", known, MARKET, str(entry.get("installLocation") or ""))

installed = os.path.join(HOME, ".claude", "plugins", "installed_plugins.json")
data = load(installed)
if data is not None:
    plugins = data.get("plugins")
    if isinstance(plugins, dict) and PLUGIN in plugins:
        entries = plugins[PLUGIN]
        if not isinstance(entries, list):
            entries = [entries]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            install_path = str(entry.get("installPath") or "")
            emit("plugin", installed, PLUGIN, str(entry.get("scope") or "?"),
                 str(entry.get("version") or "?"), install_path)
            if install_path:
                # A plugin ships its own MCP config, which ranks below user scope.
                plugin_mcp = os.path.join(install_path, ".mcp.json")
                pdata = load(plugin_mcp)
                if pdata is not None:
                    walk_servers(plugin_mcp, "mcpServers",
                                 pdata.get("mcpServers"), "plugin", "-")

# --- other clients
cursor = os.path.join(HOME, ".cursor", "mcp.json")
data = load(cursor)
if data is not None:
    walk_servers(cursor, "mcpServers", data.get("mcpServers"), "client:cursor", "-")

if sys.platform == "darwin":
    desktop = os.path.join(
        HOME, "Library", "Application Support", "Claude",
        "claude_desktop_config.json",
    )
    data = load(desktop)
    if data is not None:
        walk_servers(desktop, "mcpServers", data.get("mcpServers"),
                     "client:claude-desktop", "-")

# --- project scope: .mcp.json plus project-local settings
for pdir in project_dirs:
    mcp_json = os.path.join(pdir, ".mcp.json")
    data = load(mcp_json)
    if data is not None:
        emit("projectfile", pdir, mcp_json)
        walk_servers(mcp_json, "mcpServers", data.get("mcpServers"), "project", pdir)
    for name in ("settings.json", "settings.local.json"):
        scan_settings(os.path.join(pdir, ".claude", name), pdir)

# --- one group per distinct registration, so a repo with many worktrees does
# not print the same stdio entry dozens of times
groups = {}
for match, name, scope, projdir, path, kind, endpoint, command in MCP_ROWS:
    key = (match, name, scope, kind, endpoint, command)
    where = path if projdir == "-" else "%s  (project %s)" % (path, projdir)
    groups.setdefault(key, []).append(where)
for (match, name, scope, kind, endpoint, command), places in groups.items():
    samples = places[:3] + [""] * (3 - len(places[:3]))
    emit("mcpgroup", match, name, scope, kind, endpoint, command,
         len(places), *samples)
PY
}

# Conflict ranking reads the probe's own records back, so the precedence
# constant lives next to nothing else that could disagree with it.
analyse_conflicts() {
    [ -n "$PYTHON3" ] || return 0
    # Captured rather than appended in place: the analysis reads the same file
    # its output extends.
    _conflicts=$("$PYTHON3" - "$RECORDS" <<'PY'
import sys

# Claude Code resolves a duplicate server *name* by source, taking the whole
# entry from the highest-precedence one; fields are not merged across scopes.
# Two entries under different names both start, which is the case the
# one-server invariant exists to catch.
PRECEDENCE = ["local", "project", "user", "plugin"]

with open(sys.argv[1], encoding="utf-8") as fh:
    lines = fh.read().splitlines()

rows = []
disabled = set()
for line in lines:
    parts = line.split("\t")
    if parts[0] == "mcp" and parts[1] == "definite" and parts[3] in PRECEDENCE:
        rows.append({"name": parts[2], "scope": parts[3], "dir": parts[4],
                     "file": parts[5], "kind": parts[6], "endpoint": parts[7]})
    elif parts[0] == "disabledjson":
        disabled.add(parts[1])

dirs = sorted({r["dir"] for r in rows if r["dir"] != "-"})
if not dirs and rows:
    dirs = ["-"]

# Directories whose conflict has the same shape share one report block: a repo
# with a dozen worktrees hits the identical clash in every one of them.
shapes = {}
for pdir in dirs:
    applicable = [
        r for r in rows
        if r["dir"] == pdir or (r["dir"] == "-" and r["scope"] in ("user", "plugin"))
    ]
    by_name = {}
    for row in applicable:
        by_name.setdefault(row["name"], []).append(row)
    shape = []
    active = 0
    shadowed = 0
    for name in sorted(by_name):
        candidates = sorted(by_name[name], key=lambda r: PRECEDENCE.index(r["scope"]))
        taken = False
        for row in candidates:
            if row["scope"] == "project" and (pdir in disabled or "-" in disabled):
                status = "rejected by disabledMcpjsonServers"
                shadowed += 1
            elif not taken:
                status = "active"
                taken = True
                active += 1
            else:
                status = "shadowed"
                shadowed += 1
            # A dir-specific file is left out of the shape so identical clashes
            # in sibling worktrees collapse into one block.
            shape.append((name, row["scope"], row["kind"], row["endpoint"], status,
                          row["file"] if row["dir"] == "-" else ""))
    if active < 2 and shadowed == 0:
        continue
    if active >= 2 and shadowed:
        reason = "more than one server is active here, and others are shadowed"
    elif active >= 2:
        reason = "more than one server is active here"
    else:
        reason = "one definition shadows another"
    shapes.setdefault((tuple(shape), reason), []).append(pdir)


def out(*fields):
    # "-" for empty, as in the probe: tab is IFS whitespace to the shell.
    sys.stdout.write("\t".join(str(f) if str(f) else "-" for f in fields) + "\n")


for gid, ((shape, reason), members) in enumerate(shapes.items()):
    samples = members[:3] + [""] * (3 - len(members[:3]))
    out("conflictgroup", gid, len(members), *samples, reason)
    for name, scope, kind, endpoint, status, source in shape:
        out("conflictrow", gid, name, scope, kind, endpoint, status, source)
PY
)
    if [ -n "$_conflicts" ]; then
        printf '%s\n' "$_conflicts" >>"$RECORDS"
    fi
}

# ---------------------------------------------------------------- detectors

scan_binaries() {
    section "Executables on PATH"
    for _bin in pipefy "$SERVER_BINARY"; do
        _rank=0
        while IFS= read -r _dir; do
            [ -n "$_dir" ] || continue
            _candidate="$_dir/$_bin"
            { [ -f "$_candidate" ] && [ -x "$_candidate" ]; } || continue
            _rank=$((_rank + 1))
            if [ "$_rank" -eq 1 ]; then
                finding "$_bin -> $_candidate (first on PATH, this is what runs)"
            else
                finding "$_bin -> $_candidate (shadowed by the entry above)"
            fi
            _origin=$(resolve_link "$_candidate")
            if [ "$_origin" != "$_candidate" ]; then
                detail "resolves to $_origin"
            fi
            # A pyvenv.cfg beside the bin directory means this belongs to a
            # project's virtualenv, not to an install of the toolkit.
            _venv="${_dir%/*}"
            if [ "${_dir##*/}" = "bin" ] && [ -f "$_venv/pyvenv.cfg" ]; then
                detail "project virtualenv binary from $_venv, not an installed artifact"
                detail "leave it alone: it belongs to that checkout and goes with its .venv"
            fi
        done <<EOF
$(path_dirs)
EOF
        if [ "$_rank" -eq 0 ]; then
            note "$_bin: not on PATH"
        elif [ "$_rank" -gt 1 ]; then
            detail "$_rank copies on PATH; removing one leaves the others"
        fi
    done
}

scan_uv_tools() {
    section "uv tool environments"
    if ! command -v uv >/dev/null 2>&1; then
        note "uv not on PATH; no uv tool environments to report"
        return 0
    fi
    if [ -n "${UV_TOOL_DIR:-}" ]; then
        detail "UV_TOOL_DIR=$UV_TOOL_DIR"
    fi
    _listing=$(uv tool list 2>/dev/null) || _listing=""
    for _tool in pipefy-cli "$SERVER_BINARY"; do
        # `uv tool list` prints "<name> v<version>" per tool with its
        # executables indented under it. Match the first field exactly.
        if printf '%s\n' "$_listing" \
            | awk -v t="$_tool" '$1 == t { f = 1 } END { exit !f }'; then
            finding "uv tool installed: $_tool"
        else
            note "uv tool not installed: $_tool"
        fi
    done
    if [ -z "${UV_TOOL_DIR:-}" ]; then
        detail "install.sh --prefix sets UV_TOOL_DIR and records it nowhere, so a tool"
        detail "installed under a custom prefix is invisible unless that prefix is exported"
    fi
}

# Reported, never acted on. There are two distinct ways to lose data here, so
# both are spelled out wherever the cache is mentioned.
scan_uv_cache() {
    section "uv cache"
    _cache="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"
    if [ ! -d "$_cache" ]; then
        note "no uv cache at $_cache"
        return 0
    fi
    note "cache directory: $_cache"
    if command -v find >/dev/null 2>&1 && [ -d "$_cache/archive-v0" ]; then
        _editable=$(find "$_cache/archive-v0" -maxdepth 2 -name '*_editable_impl_*.pth' 2>/dev/null \
            | awk 'END { print NR }')
        if [ "${_editable:-0}" -gt 0 ]; then
            note "$_editable editable-install entries left by 'uv sync' / 'uv build' on local repos"
            detail "These belong to those repositories' virtualenvs, not to this toolkit."
            detail "Do not chase them: removing one breaks its checkout until the next sync,"
            detail "and 'uv cache clean <package>' does not remove them anyway."
        fi
    fi
    detail "Never run a bare 'uv cache clean': with no package argument it clears the"
    detail "cache for every package on this machine. uv also hardlinks tool environments"
    detail "into the cache, so clearing it breaks an already-running MCP server with a"
    detail "missing-module error until its client restarts. Prefer 'uv cache prune', and"
    detail "only while no server is running."
}

scan_registrations() {
    section "MCP registrations"
    detail "matched on what an entry runs: the $SERVER_BINARY command, a known"
    detail "runner invoking it, or the host $HOSTED_HOST. The registration"
    detail "key is reported as data, never used as the matching criterion."
    if [ -z "$PYTHON3" ]; then
        uninspected "JSON client configs not inspected — python3 unavailable"
        detail "affects the Claude Code, Cursor and Claude Desktop configs, the plugin"
        detail "registry, and every project .mcp.json"
        scan_codex
        return 0
    fi
    _any=0
    _maybe=0
    while IFS="$TAB" read -r _ _match _name _scope _kind _endpoint _command _count _s1 _s2 _s3; do
        [ -n "${_match:-}" ] || continue
        if [ "$_match" != "definite" ]; then
            _maybe=$((_maybe + 1))
            continue
        fi
        _any=$((_any + 1))
        if [ "$_count" -gt 1 ]; then
            finding "$_scope scope, named '$_name': $_kind  $_endpoint  ($_count locations)"
        else
            finding "$_scope scope, named '$_name': $_kind  $_endpoint"
        fi
        for _place in "$_s1" "$_s2" "$_s3"; do
            is_set "$_place" || continue
            detail "in $_place"
        done
        if [ "$_count" -gt 3 ]; then
            detail "and $((_count - 3)) more"
        fi
        if is_set "$_command" && ! command -v "$_command" >/dev/null 2>&1; then
            detail "broken: command '$_command' does not resolve on PATH"
        fi
    done <<EOF
$(records mcpgroup)
EOF
    if [ "$_any" -eq 0 ]; then
        note "no registration in any JSON client config runs this toolkit"
    fi
    if [ "$_maybe" -gt 0 ]; then
        scan_possible_registrations
    fi
    while IFS="$TAB" read -r _ _dir _file; do
        [ -n "${_dir:-}" ] || continue
        note "'$CANONICAL_NAME' listed in disabledMcpjsonServers ($_file)"
        detail "a project-scope .mcp.json entry under that name is rejected for $_dir"
    done <<EOF
$(records disabledjson)
EOF
    scan_project_files
    scan_codex
}

# Entries carrying a weak signal — a name in this toolkit's namespace, or one
# of its environment variables — that do not run anything identifiable.
# Reported for the reader to judge, never claimed as ours.
scan_possible_registrations() {
    while IFS="$TAB" read -r _ _match _name _scope _kind _endpoint _command _count _s1 _s2 _s3; do
        [ "${_match:-}" = "possible" ] || continue
        case "$_kind" in
            http|streamable-http|sse|ws)
                finding "unverified: '$_name' at $_scope scope is an HTTP registration that is not the documented hosted endpoint" ;;
            *)
                finding "unverified: '$_name' at $_scope scope does not run $SERVER_BINARY" ;;
        esac
        detail "$_kind  $_endpoint"
        for _place in "$_s1" "$_s2" "$_s3"; do
            is_set "$_place" || continue
            detail "in $_place"
        done
        if [ "$_count" -gt 3 ]; then
            detail "and $((_count - 3)) more"
        fi
        detail "decide whether this one is yours; this script will not guess"
    done <<EOF
$(records mcpgroup)
EOF
}

# A .mcp.json under version control is the repository's own source. Report it;
# never machine-edit it.
scan_project_files() {
    command -v git >/dev/null 2>&1 || return 0
    _tracked=0
    _first=""
    while IFS="$TAB" read -r _ _dir _file; do
        [ -n "${_dir:-}" ] || continue
        if git -C "$_dir" ls-files --error-unmatch .mcp.json >/dev/null 2>&1; then
            _tracked=$((_tracked + 1))
            [ -n "$_first" ] || _first="$_file"
        fi
    done <<EOF
$(records projectfile)
EOF
    if [ "$_tracked" -gt 0 ]; then
        detail "$_tracked project .mcp.json files are git-tracked, starting with $_first."
        detail "Editing one is not durable: the next checkout, branch switch, or stash pop"
        detail "restores it from the index. Use disabledMcpjsonServers instead."
    fi
}

# Codex config is TOML and install.sh appends its section blind, so detection
# keys on the section header. Every section is then matched on what it runs, so
# a server registered under another name is found too.
scan_codex() {
    _codex="$HOME/.codex/config.toml"
    if [ ! -f "$_codex" ]; then
        note "codex: no $_codex"
        return 0
    fi
    _hit=0
    while IFS="$TAB" read -r _name _command _url _args; do
        [ -n "${_name:-}" ] || continue
        if is_set "$_url"; then
            [ "$(url_host "$_url")" = "$HOSTED_HOST" ] || continue
            _hit=$((_hit + 1))
            finding "codex, section [mcp_servers.$_name]: $_url"
        else
            is_set "$_command" || continue
            # Word splitting is how the flattened argument list is re-read.
            # shellcheck disable=SC2086
            stdio_matches "$_command" $_args || continue
            _hit=$((_hit + 1))
            if is_set "$_args"; then
                finding "codex, section [mcp_servers.$_name]: $_command $_args"
            else
                finding "codex, section [mcp_servers.$_name]: $_command"
            fi
            if ! command -v "$_command" >/dev/null 2>&1; then
                detail "broken: command '$_command' does not resolve on PATH"
            fi
        fi
        detail "in $_codex"
    done <<EOF
$(codex_sections "$_codex")
EOF
    if [ "$_hit" -eq 0 ]; then
        note "codex: no section in $_codex runs this toolkit"
    fi
}

# One tab-separated line per [mcp_servers.<name>] section: name, command, url,
# and args flattened to a space-separated list.
codex_sections() {
    awk '
        # "-" for an empty field: tab is IFS whitespace, so the consuming shell
        # would collapse a run of tabs and shift columns.
        function dash(v) { return v == "" ? "-" : v }
        function flush() {
            if (sec != "")
                printf "%s\t%s\t%s\t%s\n", sec, dash(cmd), dash(url), dash(args)
            sec = ""; cmd = ""; url = ""; args = ""
        }
        /^[ \t]*\[/ {
            flush()
            if ($0 ~ /^\[mcp_servers\.[^.]+\]$/) {
                sec = substr($0, 14, length($0) - 14)
            }
            next
        }
        sec != "" && /^[ \t]*command[ \t]*=/ {
            v = $0; sub(/^[^=]*=[ \t]*/, "", v); gsub(/"/, "", v); cmd = v; next
        }
        sec != "" && /^[ \t]*url[ \t]*=/ {
            v = $0; sub(/^[^=]*=[ \t]*/, "", v); gsub(/"/, "", v); url = v; next
        }
        sec != "" && /^[ \t]*args[ \t]*=/ {
            v = $0; sub(/^[^=]*=[ \t]*/, "", v)
            gsub(/\[|\]|"/, "", v); gsub(/,/, " ", v); args = v; next
        }
        END { flush() }
    ' "$1"
}

scan_conflicts() {
    section "Scope conflicts"
    if [ -z "$PYTHON3" ]; then
        uninspected "not inspected — python3 unavailable"
        return 0
    fi
    _any=0
    while IFS="$TAB" read -r _ _gid _count _d1 _d2 _d3 _reason; do
        [ -n "${_gid:-}" ] || continue
        _any=1
        if [ "$_d1" = "-" ]; then
            finding "$_reason (every project)"
        elif [ "$_count" -gt 1 ]; then
            finding "$_reason (in $_count projects)"
        else
            finding "$_reason: $_d1"
        fi
        if [ "$_count" -gt 1 ]; then
            for _d in "$_d1" "$_d2" "$_d3"; do
                is_set "$_d" || continue
                detail "$_d"
            done
            if [ "$_count" -gt 3 ]; then
                detail "and $((_count - 3)) more"
            fi
        fi
        while IFS="$TAB" read -r _ _rgid _name _scope _kind _endpoint _status _file; do
            [ "${_rgid:-}" = "$_gid" ] || continue
            detail "  '$_name' at $_scope scope: $_kind $_endpoint  [$_status]"
            if is_set "$_file"; then
                detail "    from $_file"
            fi
        done <<ROWS
$(records conflictrow)
ROWS
    done <<EOF
$(records conflictgroup)
EOF
    if [ "$_any" -eq 0 ]; then
        note "at most one registration is active per project, with nothing shadowed"
    else
        detail "precedence resolves one name across scopes — local > project > user >"
        detail "plugin, whole entry, no field merging. It does not resolve across names:"
        detail "two differently named definitions both start, which is the case the"
        detail "one-server invariant exists to catch."
    fi
}

scan_plugin() {
    section "Claude Code plugin and marketplace"
    _clone="$HOME/.claude/plugins/marketplaces/$MARKETPLACE_ID"
    if [ -z "$PYTHON3" ]; then
        uninspected "plugin registry not inspected — python3 unavailable"
        if [ -d "$_clone" ]; then
            finding "marketplace clone on disk: $_clone"
        fi
        return 0
    fi
    _registered=0
    while IFS="$TAB" read -r _ _file _key _location; do
        [ -n "${_file:-}" ] || continue
        _registered=1
        finding "marketplace registered: $_key in $_file"
        if is_set "$_location"; then
            detail "clone at $_location"
        fi
    done <<EOF
$(records marketplace)
EOF
    _installed=0
    while IFS="$TAB" read -r _ _file _id _scope _version _path; do
        [ -n "${_file:-}" ] || continue
        _installed=1
        finding "plugin installed: $_id ($_scope scope, version $_version)"
        detail "in $_file"
        if is_set "$_path"; then
            detail "files at $_path"
        fi
    done <<EOF
$(records plugin)
EOF
    while IFS="$TAB" read -r _ _file _key _state; do
        [ -n "${_file:-}" ] || continue
        finding "plugin flag: $_key = $_state in $_file"
    done <<EOF
$(records pluginflag)
EOF
    while IFS="$TAB" read -r _ _file _key; do
        [ -n "${_file:-}" ] || continue
        finding "plugin usage record: $_key in $_file"
    done <<EOF
$(records pluginusage)
EOF
    if [ -d "$_clone" ]; then
        if [ "$_registered" -eq 0 ]; then
            finding "orphan clone: $_clone exists with no marketplace registration"
        fi
    else
        note "no marketplace clone at $_clone"
    fi
    if [ "$_registered" -eq 1 ] && [ "$_installed" -eq 0 ]; then
        finding "orphan registration: marketplace '$MARKETPLACE_ID' is registered but no plugin is installed"
        detail "'/plugin uninstall' alone no-ops here; the marketplace must go too"
    fi
    if [ "$_registered" -eq 1 ] || [ "$_installed" -eq 1 ]; then
        detail "Removing a marketplace is not necessarily durable: a later session re-adds it"
        detail "from a settings file that still lists it under extraKnownMarketplaces, or from"
        detail "a still-enabled plugin that needs it. Clear those entries too, then confirm"
        detail "with a fresh session rather than trusting the first removal."
    fi
    if [ "$_registered" -eq 0 ] && [ "$_installed" -eq 0 ]; then
        note "no plugin or marketplace registration"
    fi
}

# Which store actually holds the session right now, and what changing it costs.
scan_keychain_backend() {
    _backend="auto"
    _source="default"
    _toml=$(config_toml_path)
    if [ -f "$_toml" ]; then
        # A top-level key, so stop at the first table header.
        _from_toml=$(awk '
            /^[ \t]*\[/ { exit }
            /^[ \t]*keychain_backend[ \t]*=/ {
                sub(/^[^=]*=[ \t]*/, ""); gsub(/"/, ""); gsub(/[ \t]+$/, "")
                print; exit
            }
        ' "$_toml") || _from_toml=""
        if [ -n "$_from_toml" ]; then
            _backend="$_from_toml"
            _source="$_toml"
        fi
    fi
    if [ -n "${PIPEFY_KEYCHAIN_BACKEND:-}" ]; then
        _backend="$PIPEFY_KEYCHAIN_BACKEND"
        _source="the process environment"
    fi
    case "$_backend" in
        file)
            note "effective session store: the file backend at $CONFIG_DIR/keyring.cfg" ;;
        auto)
            note "effective session store: the OS keychain (no override in effect)" ;;
        *)
            # Never echo the raw value; an unexpected one is reported as such.
            note "effective session store: PIPEFY_KEYCHAIN_BACKEND holds an unrecognized value" ;;
    esac
    if [ "$_source" != "default" ]; then
        finding "PIPEFY_KEYCHAIN_BACKEND is set in $_source"
        detail "Removing that setting changes which store holds the session: the next login"
        detail "writes to the OS keychain instead, while anything already in keyring.cfg"
        detail "stays there, still signed in and invisible to a keychain-only sweep."
    fi
    detail "both stores are checked below, whichever one is effective"
}

scan_credentials() {
    section "Stored credentials"
    scan_keychain_backend
    case "$OS" in
        Darwin) scan_keychain_macos ;;
        Linux) scan_keychain_linux ;;
    esac
    _cfg="$CONFIG_DIR/keyring.cfg"
    if [ ! -f "$_cfg" ]; then
        note "no file-backend store at $_cfg"
        return 0
    fi
    finding "file keyring backend: $_cfg stores refresh tokens in plaintext"
    # An INI whose section is the keyring service and whose keys are escaped
    # account names. Values sit on indented continuation lines and are not read.
    while IFS= read -r _acct; do
        [ -n "$_acct" ] || continue
        detail "account: $_acct"
    done <<EOF
$(keyring_cfg_accounts "$_cfg")
EOF
}

keyring_cfg_accounts() {
    awk -v svc="$KEYCHAIN_SERVICE" '
        function hexdigit(c,   i) { i = index("0123456789abcdef", tolower(c)); return i - 1 }
        function unescape(s,   out, i, n, c, a, b) {
            out = ""; i = 1; n = length(s)
            while (i <= n) {
                c = substr(s, i, 1)
                if (c == "_" && i + 2 <= n) {
                    a = hexdigit(substr(s, i + 1, 1)); b = hexdigit(substr(s, i + 2, 1))
                    if (a >= 0 && b >= 0) { out = out sprintf("%c", a * 16 + b); i += 3; continue }
                }
                out = out c; i++
            }
            return out
        }
        /^\[/ { inside = ($0 == "[" svc "]"); next }
        inside && /^[^ \t#;]/ && index($0, "=") > 0 {
            key = $0; sub(/[ \t]*=.*$/, "", key); print unescape(key)
        }
    ' "$1"
}

scan_keychain_macos() {
    if ! command -v security >/dev/null 2>&1; then
        uninspected "keychain not inspected — 'security' not on PATH"
        return 0
    fi
    # Neither -w nor -g, so this reads item attributes only: it never unlocks a
    # secret and never raises a keychain access prompt.
    if ! security find-generic-password -s "$KEYCHAIN_SERVICE" >/dev/null 2>&1; then
        note "keychain: no item with service '$KEYCHAIN_SERVICE'"
        return 0
    fi
    # find-generic-password returns the first match only. Enumerating the rest
    # needs dump-keychain, which lists attributes for every item and, without
    # -d, never reads a secret.
    _found=0
    while IFS= read -r _acct; do
        [ -n "$_acct" ] || continue
        _found=1
        finding "keychain: service $KEYCHAIN_SERVICE, account $_acct"
    done <<EOF
$(security dump-keychain 2>/dev/null | keychain_accounts)
EOF
    if [ "$_found" -eq 0 ]; then
        finding "keychain: at least one item with service '$KEYCHAIN_SERVICE' (accounts not enumerated)"
    else
        detail "one item per (issuer, client_id); a non-production PIPEFY_AUTH_URL adds more"
    fi
}

# Parse `security dump-keychain` records: emit the account attribute of every
# generic-password item whose service attribute is exactly our service.
keychain_accounts() {
    awk -v svc="\"svce\"<blob>=\"$KEYCHAIN_SERVICE\"" '
        function flush() { if (genp && match_svc && acct != "") print acct }
        /^keychain: / { flush(); genp = 0; match_svc = 0; acct = "" }
        /^class: "genp"/ { genp = 1 }
        /^[ \t]*"svce"<blob>=/ { line = $0; sub(/^[ \t]+/, "", line); if (line == svc) match_svc = 1 }
        /^[ \t]*"acct"<blob>="/ { acct = $0; sub(/^[ \t]*"acct"<blob>="/, "", acct); sub(/"$/, "", acct) }
        END { flush() }
    '
}

scan_keychain_linux() {
    if ! command -v secret-tool >/dev/null 2>&1; then
        note "keychain: 'secret-tool' not on PATH; no Secret Service to query"
        return 0
    fi
    # No --unlock, and the output is reduced to the username attribute, so no
    # secret is ever printed. A locked collection can still raise the desktop's
    # own unlock dialog, which secret-tool offers no flag to suppress.
    _found=0
    while IFS= read -r _acct; do
        [ -n "$_acct" ] || continue
        _found=1
        finding "keychain: service $KEYCHAIN_SERVICE, account $_acct"
    done <<EOF
$(secret-tool search service "$KEYCHAIN_SERVICE" 2>/dev/null \
    | awk -F' = ' '$1 == "attribute.username" { print $2 }')
EOF
    if [ "$_found" -eq 0 ]; then
        note "keychain: no Secret Service item with service '$KEYCHAIN_SERVICE'"
    fi
}

scan_config_dir() {
    section "Configuration directory"
    note "resolves to $CONFIG_DIR"
    _toml=$(config_toml_path)
    if [ "$_toml" != "$CONFIG_DIR/config.toml" ]; then
        note "PIPEFY_CONFIG_FILE relocates config.toml to $_toml"
    fi
    if [ ! -d "$CONFIG_DIR" ]; then
        note "does not exist"
        return 0
    fi
    _empty=1
    while IFS= read -r _name; do
        [ -n "$_name" ] || continue
        _empty=0
        case "$_name" in
            config.toml)
                finding "$CONFIG_DIR/$_name (user-authored; never remove without consent)" ;;
            keyring.cfg)
                note "$CONFIG_DIR/$_name (reported under stored credentials)" ;;
            *)
                finding "$CONFIG_DIR/$_name" ;;
        esac
    done <<EOF
$(ls -A "$CONFIG_DIR" 2>/dev/null)
EOF
    if [ "$_empty" -eq 1 ]; then
        note "exists but is empty"
    fi
    detail "the next CLI invocation recreates this directory, so removing it is not idempotent"
}

scan_environment() {
    section "Environment variables"
    _live=0
    for _name in $CRED_ENV_NAMES; do
        if env_is_set "$_name"; then
            _live=1
            finding "set in this process environment: $_name (credential)"
        fi
    done
    for _name in $CONFIG_ENV_NAMES; do
        if env_is_set "$_name"; then
            _live=1
            finding "set in this process environment: $_name (configuration)"
        fi
    done
    if [ "$_live" -eq 1 ]; then
        detail "a child process cannot unset a variable in its parent shell; unset these"
        detail "yourself or start a new shell"
    else
        note "none set in this process environment"
    fi
    scan_shell_rc
    scan_env_blocks
}

# Exact-name lookup, by literal prefix rather than a pattern: `env | grep -i
# pipefy` matches PWD for anyone working in a directory named after it.
env_is_set() {
    env | awk -v n="$1" 'index($0, n "=") == 1 { f = 1 } END { exit !f }'
}

scan_shell_rc() {
    _hit=0
    for _rc in \
        "$HOME/.profile" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.bash_login" \
        "$HOME/.zshenv" "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.kshrc"
    do
        [ -f "$_rc" ] || continue
        for _name in $CRED_ENV_NAMES $CONFIG_ENV_NAMES; do
            # An assignment to the exact name, optionally exported. Line numbers
            # only, so no value ever reaches the report.
            _lines=$(grep -nE "^[[:space:]]*(export[[:space:]]+)?$_name=" "$_rc" \
                | cut -d: -f1 | tr '\n' ' ') || _lines=""
            [ -n "$_lines" ] || continue
            _hit=1
            finding "$_name assigned in $_rc (line ${_lines% })"
        done
    done
    _fish="${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish"
    if [ -f "$_fish" ]; then
        for _name in $CRED_ENV_NAMES $CONFIG_ENV_NAMES; do
            _lines=$(grep -nE "^[[:space:]]*set([[:space:]]+-[A-Za-z]+)*[[:space:]]+${_name}[[:space:]]" "$_fish" \
                | cut -d: -f1 | tr '\n' ' ') || _lines=""
            [ -n "$_lines" ] || continue
            _hit=1
            finding "$_name assigned in $_fish (line ${_lines% })"
        done
    fi
    if [ "$_hit" -eq 0 ]; then
        note "none assigned in a shell rc file"
    fi
}

scan_env_blocks() {
    if [ -z "$PYTHON3" ]; then
        uninspected "client config env blocks not inspected — python3 unavailable"
        return 0
    fi
    _hit=0
    while IFS="$TAB" read -r _ _file _keypath _name _tier; do
        [ -n "${_file:-}" ] || continue
        _hit=1
        finding "$_name ($_tier) in $_file at $_keypath"
    done <<EOF
$(records envkey)
EOF
    if [ "$_hit" -eq 0 ]; then
        note "none in a client config env block"
    fi
}

scan_completions() {
    section "Shell completions"
    _hit=0
    for _f in \
        "$HOME/.bash_completions/pipefy.sh" \
        "$HOME/.zfunc/_pipefy" \
        "${XDG_CONFIG_HOME:-$HOME/.config}/fish/completions/pipefy.fish"
    do
        [ -f "$_f" ] || continue
        _hit=1
        finding "$_f"
    done
    if [ -f "$HOME/.bashrc" ]; then
        # A source directive naming our exact script, not a line mentioning it.
        _lines=$(grep -nE '^[[:space:]]*(source|\.)[[:space:]]+.*/\.bash_completions/pipefy\.sh' "$HOME/.bashrc" \
            | cut -d: -f1 | tr '\n' ' ') || _lines=""
        if [ -n "$_lines" ]; then
            _hit=1
            finding "$HOME/.bashrc sources the completion script (line ${_lines% })"
        fi
    fi
    if [ -f "$HOME/.zfunc/_pipefy" ] && [ -f "$HOME/.zshrc" ]; then
        # The zsh installer only adds a shared ~/.zfunc to fpath, so this line
        # may belong to another tool. Reported, never claimed as ours.
        _lines=$(grep -nE '^[[:space:]]*fpath\+=' "$HOME/.zshrc" \
            | cut -d: -f1 | tr '\n' ' ') || _lines=""
        if [ -n "$_lines" ]; then
            detail "$HOME/.zshrc line ${_lines% } adds ~/.zfunc to fpath; shared with other tools"
        fi
    fi
    if [ "$_hit" -eq 0 ]; then
        note "no pipefy completion files installed"
    fi
}

scan_skills() {
    section "Skills"
    _dir="$HOME/.claude/skills"
    if [ ! -d "$_dir" ]; then
        note "no $_dir"
        return 0
    fi
    _hit=0
    for _skill in "$_dir"/pipefy-*; do
        # A directory holding a SKILL.md, under the name `npx skills add`
        # gives this catalog's skills.
        [ -f "$_skill/SKILL.md" ] || continue
        _hit=$((_hit + 1))
        detail "$(basename "$_skill")"
    done
    if [ "$_hit" -eq 0 ]; then
        note "no pipefy-* skills in $_dir"
    else
        finding "$_hit pipefy-* skills installed under $_dir"
    fi
}

report_probe_errors() {
    [ -n "$PYTHON3" ] || return 0
    while IFS="$TAB" read -r _ _file _message; do
        [ -n "${_file:-}" ] || continue
        uninspected "$_file: $_message"
    done <<EOF
$(records err)
EOF
}

print_next_steps() {
    say ""
    say "Removal is not available in this version — this run only reported state."
    say "Nothing on this machine was changed."
    say ""
    say "To reverse the pieces by hand until it is:"
    say "  local install       uv tool uninstall pipefy-cli $SERVER_BINARY"
    say "  Claude Code MCP     claude mcp remove <name> -s user   (also -s local)"
    say "  Claude Code plugin  /plugin uninstall $PLUGIN_ID, then"
    say "                      /plugin marketplace remove $MARKETPLACE_ID"
    say "  other clients       delete the mcpServers.<name> key, or the"
    say "                      [mcp_servers.<name>] section for Codex"
    say "  credentials         pipefy auth logout"
    say "  hosted OAuth        claude mcp logout <name>   (per server; if that"
    say "                      verb is unavailable, /mcp -> the server ->"
    say "                      Clear authentication)"
    say ""
    say "Use the names this report printed: a registration can be called anything."
    say "Never run a bare 'uv cache clean'. With no package argument it clears the"
    say "cache for every package, and uv hardlinks tool environments into it, so an"
    say "already-running MCP server breaks until its client restarts."
    say "A git-tracked .mcp.json is the repository's own source: git restores it, so"
    say "disable it through disabledMcpjsonServers instead of editing the file."
}

main() {
    parse_args "$@"
    refuse_root
    detect_platform
    resolve_config_dir
    PYTHON3=$(command -v python3 2>/dev/null) || PYTHON3=""

    RECORDS=$(mktemp "${TMPDIR:-/tmp}/pipefy-scan.XXXXXX") \
        || err "mktemp failed (TMPDIR=${TMPDIR:-/tmp})"
    trap 'rm -f "$RECORDS"' EXIT INT TERM

    say "Pipefy toolkit scan"
    say "  home:      $HOME"
    say "  platform:  $OS"
    say "  config:    $CONFIG_DIR"
    if [ -n "$PYTHON3" ]; then
        say "  python3:   $PYTHON3"
    else
        say "  python3:   not found — JSON sources will not be inspected"
    fi
    if [ -n "$CLIENT" ]; then
        say "  client:    $CLIENT (detection sweeps every client regardless)"
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
        say "  --dry-run has no effect: this version only scans."
    fi

    set --
    while IFS= read -r _pdir; do
        [ -n "$_pdir" ] || continue
        set -- "$@" "$_pdir"
    done <<EOF
$(project_dirs)
EOF
    if [ -n "$PYTHON3" ]; then
        # A crashed probe leaves an incomplete record stream, which must not read
        # as an empty one: fall back to the no-python3 path so every JSON source
        # reports "not inspected" and the run exits 2.
        run_json_probe "$@" || {
            warn "python3 probe failed; JSON sources left uninspected"
            PYTHON3=""
        }
    fi
    analyse_conflicts

    scan_binaries
    scan_uv_tools
    scan_uv_cache
    scan_registrations
    scan_conflicts
    scan_plugin
    scan_credentials
    scan_config_dir
    scan_environment
    scan_completions
    scan_skills
    report_probe_errors

    section "Summary"
    if [ "$FINDINGS" -eq 0 ]; then
        say "  no Pipefy toolkit state found"
    else
        say "  $FINDINGS findings"
    fi
    if [ "$SCAN_ERRORS" -gt 0 ]; then
        say "  $SCAN_ERRORS sources could not be inspected"
    fi

    print_next_steps

    if [ "$SCAN_ERRORS" -gt 0 ]; then
        exit 2
    fi
    if [ "$FINDINGS" -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main "$@"
