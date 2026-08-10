#!/bin/sh
# uninstall.sh — report and remove Pipefy toolkit state across every install
# channel and MCP client.
#
# `--scan` reads and reports; it never removes, moves, or edits anything, and
# the only paths it writes are tempfiles holding its own record streams. Any
# other invocation scans, prints the plan it derived from that scan, asks for
# approval in tiers, removes what was approved, and scans again.
#
# Channels: the Claude Code plugin, a local install (install.sh / uv tool /
# uvx), and the hosted HTTP server. Clients come from CLIENT_TABLE below;
# adding one is a row there and no new code.
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
# An entry matches when *either* half of that rule fires: what it runs is this
# toolkit's server, or where it points is the hosted host. The two fields are
# read independently and a declared transport type is not a precondition for
# either, because which field a client honours differs between clients — Cursor
# and Codex read a `url` with no `type` as a remote server, Claude Code reads an
# entry with no `type` as stdio and skips it. Judging the shape by one client's
# rule leaves a registration the others do run invisible to the scan and alive
# after a teardown, so the shape is matched as written and the *report* carries
# the per-client caveat, driven off the `typed-remote` capability below.
#
# Removal uses what the scan found, including the name a registration was
# actually registered under, and every deletion goes through remove_path().
#
# Exit codes: 0 nothing found / nothing left, 1 findings remain, 2 the run
# itself failed.

set -eu

REPO="pipefy/ai-toolkit"
CANONICAL_NAME="pipefy"        # the name install.sh writes; the documented invariant
KEYCHAIN_SERVICE="pipefy"      # keyring service attribute
SERVER_BINARY="pipefy-mcp-server"
HOSTED_HOST="mcp.pipefy.com"   # the documented hosted endpoint, and the only one
RUNNERS="uvx uv npx python python3 pipx"
PLUGIN_ID="pipefy@pipefy"
MARKETPLACE_ID="pipefy"
UV_TOOLS="pipefy-cli $SERVER_BINARY"
RECEIPT_SCHEMA_MAX=1           # the newest install-receipt schema this can read

# The client table. One row per MCP client, pipe-separated because a config
# path can contain spaces:
#
#   id|platform|format|config|servers|scope|statedir|capabilities|cli
#
#   id            the --client value; the allowlist is derived from this column
#   platform      `uname -s` this row applies to, or * for every platform
#   format        json or toml — the only thing that selects a reader or an editor
#   config        the file holding server registrations; ~/ is expanded
#   servers       the key path registrations live under
#   scope         how a registration from this file is labelled in reports
#   statedir      client state directory (settings, plugin registry), or -
#   capabilities  comma-separated, see below
#   cli           the client's own command-line tool, or -
#
# Capabilities gate the client-specific work, so nothing branches on an id:
#
#   scopes         resolves one registration name across local/project/user/
#                  plugin sources, with the whole entry taken from the winner
#   plugin-system  ships a plugin and marketplace registry under statedir
#   removal-cli    ships a CLI that can remove registrations, tokens and
#                  plugins; each verb is still probed for before it is used
#   typed-remote   requires an explicit `type` on a remote entry: a `url` with
#                  no `type` is read as stdio and the server never starts. The
#                  entry is still found and still removed — this only adds a
#                  line to the report saying it was not running here
#
# Direct file editing is the baseline for every row. Delegation is the
# exception one row happens to enable.
CLIENT_TABLE="claude-code|*|json|~/.claude.json|mcpServers|user|~/.claude|scopes,plugin-system,removal-cli,typed-remote|claude
claude-desktop|Darwin|json|~/Library/Application Support/Claude/claude_desktop_config.json|mcpServers|client:claude-desktop|-|-|-
codex|*|toml|~/.codex/config.toml|mcp_servers|client:codex|-|-|-
cursor|*|json|~/.cursor/mcp.json|mcpServers|client:cursor|-|-|-"

MODE=teardown
CLIENT=""
ALLOW_ROOT=0
DRY_RUN=0
YES=0
KEEP_CREDENTIALS=0
KEEP_CONFIG=0

OS=""
CONFIG_DIR=""
RECEIPT_FILE=""
RECEIPT_STATE=""
# Everything the receipt said, merged. Path-valued lists stay escaped until the
# moment they are used, one value per line.
RCPT_PRESENT=0
RCPT_UNREADABLE=0
RCPT_TOOL_DIRS=""
RCPT_SKILL_DIRS=""
RCPT_SKILLS=""
RCPT_TOOLS=""
RCPT_CREATED=""
RCPT_TAG=""
RCPT_UV_OURS=0
RCPT_RECORDS=0
RCPT_PARTIAL=0
RCPT_FUTURE=0
RCPT_BAD=0
RCPT_JUNK=0
PYTHON3=""
RECORDS=""
PLAN=""
NOTES=""
COLLECTING=0
FINDINGS=0
SCAN_ERRORS=0
BACKUP_STAMP=""
BACKUPS=0
DONE_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
UNVERIFIED=0
REVOKED=0
CRED_DELETED=0
TIER1_OK=0
TIER2_OK=0
TIER3_OK=0
TAB=$(printf '\t')
NL='
'

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

trace() { printf '+ %s\n' "$*" >&2; }

run() {
    trace "$*"
    if [ "$DRY_RUN" -eq 1 ]; then
        return 0
    fi
    "$@"
}

confirm() {
    _cf_msg="$1"
    if [ "$YES" -eq 1 ]; then
        return 0
    fi
    if [ -t 0 ]; then
        printf '%s [y/N] ' "$_cf_msg"
        read -r _cf_reply || _cf_reply=""
    elif [ -r /dev/tty ]; then
        printf '%s [y/N] ' "$_cf_msg" >&2
        read -r _cf_reply < /dev/tty || _cf_reply=""
    else
        err "No TTY available for prompt: \"$_cf_msg\". Re-run with --yes to proceed non-interactively."
    fi
    case "$_cf_reply" in
        [yY]|[yY][eE][sS]) return 0 ;;
        *) return 1 ;;
    esac
}

# ------------------------------------------------------------- client table

# The table writes paths with a literal ~/ prefix; this is where one becomes a
# real path.
# shellcheck disable=SC2088
expand_home() {
    case "$1" in
        '~/'*) printf '%s\n' "$HOME/${1#\~/}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

# Every row, paths expanded, platform ignored. The allowlist and the help text
# both come from here, so they cannot drift apart.
all_client_rows() {
    printf '%s\n' "$CLIENT_TABLE" \
        | while IFS='|' read -r _id _plat _fmt _cfg _srv _sc _st _caps _cli; do
        [ -n "$_id" ] || continue
        printf '%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
            "$_id" "$_plat" "$_fmt" "$(expand_home "$_cfg")" "$_srv" "$_sc" \
            "$(expand_home "$_st")" "$_caps" "$_cli"
    done
}

# The rows that apply to this machine.
client_rows() {
    all_client_rows | while IFS='|' read -r _id _plat _fmt _cfg _srv _sc _st _caps _cli; do
        case "$_plat" in
            '*'|"$OS") ;;
            *) continue ;;
        esac
        printf '%s|%s|%s|%s|%s|%s|%s|%s|%s\n' \
            "$_id" "$_plat" "$_fmt" "$_cfg" "$_srv" "$_sc" "$_st" "$_caps" "$_cli"
    done
}

client_ids() {
    all_client_rows | cut -d'|' -f1
}

client_row() {
    all_client_rows | awk -F'|' -v id="$1" '$1 == id && !seen { print; seen = 1 }'
}

# Field n of a row: 1 id, 3 format, 4 config, 5 servers, 6 scope, 7 statedir,
# 8 capabilities, 9 cli.
client_field() {
    printf '%s\n' "$1" | cut -d'|' -f"$2"
}

client_has_cap() {
    printf '%s\n' "$1" | cut -d'|' -f8 | tr ',' '\n' \
        | awk -v c="$2" '$0 == c { f = 1 } END { exit !f }'
}

# The first row claiming a capability. The plugin registry, the marketplace,
# the skills directory and CLI delegation all hang off this rather than off a
# client id.
client_row_with_cap() {
    client_rows | while IFS= read -r _cr; do
        if client_has_cap "$_cr" "$1"; then
            printf '%s\n' "$_cr"
            break
        fi
    done
}

# Which client owns a config path, for --client narrowing and for reports.
client_id_for_file() {
    client_rows | awk -F'|' -v f="$1" '$4 == f && !seen { print $1; seen = 1 }'
}

# Which client reads a config file. A project .mcp.json and a plugin's own
# .mcp.json are in no client's row; the client that resolves scopes is the one
# that reads them.
client_id_reading() {
    _cir=$(client_id_for_file "$1")
    [ -n "$_cir" ] || _cir=$(client_field "$(client_row_with_cap scopes)" 1)
    printf '%s\n' "$_cir"
}

# --client narrows *registration edits* only; detection always sweeps every
# client, and tools, credentials, skills and the plugin are unaffected.
client_selected() {
    [ -z "$CLIENT" ] && return 0
    [ "$1" = "$CLIENT" ]
}

client_choice_list() {
    _ccl=$(client_ids | tr '\n' '|')
    printf '%s\n' "${_ccl%|}"
}

print_help() {
    _choices="$(client_choice_list)"
    cat <<EOF
Usage: uninstall.sh [OPTIONS]

Report Pipefy toolkit state across every install channel and MCP client, then
remove what you approve. A bare invocation scans, shows the plan, and asks.

MCP registrations are matched on what they run — the $SERVER_BINARY
command, a known runner invoking it, or the hosted endpoint's host — so an
entry registered under any name is found, and removed under that name.

Options:
  --scan              Report state and exit. Changes nothing.
  --client <id>       Limit MCP registration edits to this client's config.
                      One of: $_choices.
                      Detection always sweeps every client regardless, since
                      the point is finding state you forgot about, and tools,
                      credentials, skills and the plugin are not narrowed.
  --dry-run           Print the plan and exit without removing anything.
  --yes, -y           Approve every tier. Required with no TTY.
  --keep-credentials  Leave stored credentials alone (skips tier 2).
  --keep-config       Leave user configuration alone: config.toml, .env, and
                      non-credential PIPEFY_* settings in your own files.
  --allow-root        Allow running as root (refuses by default).
  -h, --help          Show this help.

Approval is tiered, not per action:
  [1] ours and reversible   one confirmation for the whole group
  [2] credentials           its own confirmation; cannot be undone
  [3] your own files        its own confirmation; backed up first

Exit codes:
  0  nothing found, or nothing left after removal
  1  findings remain
  2  the run itself failed (a source could not be inspected)

Examples:
  curl -LsSf https://raw.githubusercontent.com/$REPO/main/uninstall.sh \\
    | sh -s -- --scan

  ./uninstall.sh --dry-run
  ./uninstall.sh --yes --keep-config
EOF
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --scan) MODE=scan; shift ;;
            --client) [ $# -ge 2 ] || err "--client requires a value"; CLIENT="$2"; shift 2 ;;
            --client=*) CLIENT="${1#--client=}"; shift ;;
            --dry-run) DRY_RUN=1; shift ;;
            --yes|-y) YES=1; shift ;;
            --keep-credentials) KEEP_CREDENTIALS=1; shift ;;
            --keep-config) KEEP_CONFIG=1; shift ;;
            --allow-root) ALLOW_ROOT=1; shift ;;
            -h|--help) print_help; exit 0 ;;
            *) err "Unknown flag: $1 (try --help)" ;;
        esac
    done
    case "$CLIENT" in
        "") ;;
        # install.sh takes `none` and means "install without registering".
        # Teardown has no such mode: --client narrows registration edits and
        # nothing else, so `none` would edit no config while still removing the
        # binaries every config found points at. That is the stranding the
        # phase order exists to prevent, so the word is refused rather than
        # given a second meaning.
        none)
            err "--client none belongs to install.sh, where it means \"install without registering\". Teardown has no equivalent: it would remove the tools while leaving every registration pointing at a missing command. Omit --client to sweep every client, or name one of $(client_choice_list)." ;;
        *)
            [ -n "$(client_row "$CLIENT")" ] \
                || err "Invalid --client: $CLIENT (use $(client_choice_list))" ;;
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

# ------------------------------------------------------------ install receipt
#
# install.sh appends one key=value record per run to this file: the tool
# directory it used, whether it installed uv, which client entries it created
# rather than found, where the skills landed, and the release tag. Reading it
# is what makes a teardown exact instead of a guess.
#
# It is read with awk alone. python3 degrades per source in this script, and
# the receipt is one of the sources that has to keep working without it.
#
# It is also an input to a destructive program, so it is treated as untrusted
# text. A record whose schema this script does not know is skipped rather than
# half-read; a malformed line is counted and dropped; and no value from here
# ever names something to delete. Values only ever pick which directory to ask
# uv about, which skills directory to enumerate, and whether a registration the
# structural scan already found may be removed. The deletion guard in
# remove_path() is the backstop behind that, not the reason it holds.

# The receipt is installer state, not user configuration, so it lives under
# XDG_STATE_HOME rather than beside the config.toml the user wrote. That keeps
# it out of the directory this script empties and then removes, and out of the
# way of a user who backs up their own config.
resolve_receipt_path() {
    RECEIPT_STATE="${XDG_STATE_HOME:-$HOME/.local/state}/pipefy"
    RECEIPT_FILE="$RECEIPT_STATE/install-receipt"
}

# `%b` expands exactly the four sequences the writer emits, and the parser has
# already rejected any record containing a sequence it does not. The trailing
# sentinel survives the command substitution, which would otherwise eat a value
# ending in a newline.
receipt_unescape() {
    _ru=$(printf '%b.' "$1")
    printf '%s' "${_ru%.}"
}

# Merge rule: every field answers "did this machine ever get X from an
# install.sh run", and that only ever becomes true. Directories and tool names
# are therefore the union across records, `true` beats `false` for a boolean,
# and only the purely informational release tag takes the newest value. Two
# runs with different --prefix each created tool environments and both have to
# be torn down, so keeping just the last would strand the first; and a second
# run finding the entry a first run created does not un-create it.
receipt_records() {
    AW_MAX="$RECEIPT_SCHEMA_MAX" awk '
        # Every backslash the writer emits introduces \\, \n, \r or \t. A value
        # holding anything else was not written by install.sh, and expanding it
        # would invent a path.
        function okesc(s,   i, n, c, d) {
            n = length(s)
            for (i = 1; i <= n; i++) {
                c = substr(s, i, 1)
                if (c != "\\") continue
                i++
                d = substr(s, i, 1)
                if (d != "\\" && d != "n" && d != "r" && d != "t") return 0
            }
            return 1
        }
        function addset(label, v,   key) {
            key = label "=" v
            if (key in seen) return
            seen[key] = 1
            setlabel[++nset] = label
            setvalue[nset] = v
        }
        function endrec() {
            if (!started) return
            records++
            if (!complete) partial++
            if (!ok) { if (newer) future++; else unreadable++ }
            started = 0
        }
        BEGIN { max = ENVIRON["AW_MAX"] + 0 }
        {
            p = index($0, "=")
            if (p == 0) { junk++; next }
            k = substr($0, 1, p - 1)
            v = substr($0, p + 1)
            # The hyphen is in the alphabet because client ids carry one:
            # entry_created.claude-desktop is a key the writer emits, and a
            # reader that drops it silently loses the bit that says an entry
            # was already there when install.sh ran.
            if (k !~ /^[a-z][a-z0-9_.-]*$/) { junk++; next }
            if (k == "record" && v == "begin") {
                endrec()
                started = 1; expect = 1; ok = 0; complete = 0; newer = 0
                next
            }
            if (!started) { junk++; next }
            if (expect) {
                # schema is the first line of a record by construction, so a
                # reader decides whether it can read the rest before it reads
                # any of it.
                expect = 0
                if (k == "schema" && v ~ /^[0-9]+$/) {
                    if (v + 0 >= 1 && v + 0 <= max) ok = 1
                    else if (v + 0 > max) newer = 1
                }
                next
            }
            if (k == "record" && v == "end") { complete = 1; next }
            if (!ok) next
            if (!okesc(v)) { junk++; next }
            if (k == "uv_tool_dir") { addset("uv_tool_dir", v); next }
            if (k == "skills_dir") { addset("skills_dir", v); next }
            if (k == "skill") { addset("skill", v); next }
            if (k == "uv_tool") { addset("uv_tool", v); next }
            if (k == "uv_installed_by_us") { if (v == "true") uvours = 1; next }
            if (k == "release_tag") { tag = v; next }
            if (k ~ /^entry_created\./) {
                c = substr(k, 15)
                if (v == "true") created[c] = "true"
                else if (!(c in created)) created[c] = "false"
                next
            }
            # An unknown but well-formed key is ignored, not counted: the
            # schema number is what gates readability.
        }
        END {
            endrec()
            for (i = 1; i <= nset; i++)
                printf "%s\t%s\n", setlabel[i], setvalue[i]
            for (c in created)
                printf "entry_created\t%s\t%s\n", c, created[c]
            if (tag != "") printf "release_tag\t%s\n", tag
            printf "meta\trecords\t%d\n", records
            printf "meta\tpartial\t%d\n", partial
            printf "meta\tfuture\t%d\n", future
            printf "meta\tunreadable\t%d\n", unreadable
            printf "meta\tjunk\t%d\n", junk
            printf "meta\tuv_ours\t%d\n", uvours + 0
        }
    ' "$1"
}

read_receipt() {
    RCPT_PRESENT=0
    RCPT_UNREADABLE=0
    RCPT_TOOL_DIRS=""
    RCPT_SKILL_DIRS=""
    RCPT_SKILLS=""
    RCPT_TOOLS=""
    RCPT_CREATED=""
    RCPT_TAG=""
    RCPT_UV_OURS=0
    RCPT_RECORDS=0
    RCPT_PARTIAL=0
    RCPT_FUTURE=0
    RCPT_BAD=0
    RCPT_JUNK=0
    [ -e "$RECEIPT_FILE" ] || return 0
    if [ ! -f "$RECEIPT_FILE" ] || [ ! -r "$RECEIPT_FILE" ]; then
        RCPT_UNREADABLE=1
        return 0
    fi
    RCPT_PRESENT=1
    while IFS="$TAB" read -r _rr_kind _rr_a _rr_b; do
        case "${_rr_kind:-}" in
            uv_tool_dir) RCPT_TOOL_DIRS="$RCPT_TOOL_DIRS$_rr_a$NL" ;;
            skills_dir) RCPT_SKILL_DIRS="$RCPT_SKILL_DIRS$_rr_a$NL" ;;
            skill) RCPT_SKILLS="$RCPT_SKILLS$_rr_a$NL" ;;
            uv_tool) RCPT_TOOLS="$RCPT_TOOLS$_rr_a$NL" ;;
            release_tag) RCPT_TAG="$_rr_a" ;;
            entry_created) RCPT_CREATED="$RCPT_CREATED$_rr_a$TAB$_rr_b$NL" ;;
            meta)
                case "$_rr_a" in
                    records) RCPT_RECORDS="$_rr_b" ;;
                    partial) RCPT_PARTIAL="$_rr_b" ;;
                    future) RCPT_FUTURE="$_rr_b" ;;
                    unreadable) RCPT_BAD="$_rr_b" ;;
                    junk) RCPT_JUNK="$_rr_b" ;;
                    uv_ours) RCPT_UV_OURS="$_rr_b" ;;
                esac ;;
        esac
    done <<EOF
$(receipt_records "$RECEIPT_FILE")
EOF
}

# "true", "false", or empty when no run recorded anything for this client.
receipt_entry_created() {
    printf '%s' "$RCPT_CREATED" | awk -F"$TAB" -v c="$1" '$1 == c { print $2; exit }'
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

# The kinds the probe reports for an entry reached over the network.
# `untyped-url` is a url with no usable transport declaration, which Cursor and
# Codex serve over HTTP and Claude Code does not serve at all.
kind_is_remote() {
    case "$1" in
        http|streamable-http|sse|ws|untyped-url) return 0 ;;
        *) return 1 ;;
    esac
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
    SCAN_REPO="$REPO" \
    SCAN_CLIENTS="$(client_rows)" \
    "$PYTHON3" - "$@" <<'PY' >>"$RECORDS"
import json
import os
import posixpath
import sys

CANON = os.environ["SCAN_CANONICAL_NAME"]
BINARY = os.environ["SCAN_SERVER_BINARY"]
HOSTED_HOST = os.environ["SCAN_HOSTED_HOST"]
RUNNERS = set(os.environ["SCAN_RUNNERS"].split())
PLUGIN = os.environ["SCAN_PLUGIN_ID"]
MARKET = os.environ["SCAN_MARKETPLACE_ID"]
REPO = os.environ["SCAN_REPO"]
# The three spellings `skills add` records for one GitHub repository. Compared
# for equality: a skill's source is either this repository or it is not.
SKILL_SOURCES = {REPO, "https://github.com/%s" % REPO, "https://github.com/%s.git" % REPO}
CRED = set(os.environ["SCAN_ENV_CRED"].split())
CONFIG = set(os.environ["SCAN_ENV_CONFIG"].split())
PIPEFY_ENV = CRED | CONFIG

# The client table, already filtered to this platform and with ~ expanded.
CLIENTS = []
for _raw in os.environ["SCAN_CLIENTS"].splitlines():
    if not _raw.strip():
        continue
    _f = _raw.split("|")
    CLIENTS.append(
        {
            "id": _f[0],
            "format": _f[2],
            "config": _f[3],
            "servers": _f[4],
            "scope": _f[5],
            "statedir": _f[6],
            "caps": set(c for c in _f[7].split(",") if c and c != "-"),
        }
    )


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


DECLARED_REMOTE = ("http", "streamable-http", "sse", "ws")


def entry_args(entry):
    raw = entry.get("args")
    return [str(a) for a in raw] if isinstance(raw, list) else []


def runs_our_server(entry):
    """One half of the rule: the command is the binary, or a runner invoking it."""
    command = entry.get("command")
    if command is None:
        return False
    base = posixpath.basename(str(command))
    return base == BINARY or (base in RUNNERS and BINARY in entry_args(entry))


def points_at_hosted(entry):
    """The other half: an exact host comparison, never a substring search."""
    url = entry.get("url")
    return url is not None and url_host(url) == HOSTED_HOST


def describe(entry):
    """(kind, endpoint, command, args) for one entry. Values are never read.

    `kind` names the shape as written rather than a transport this decided on.
    A `url` with no usable `type` is reported as `untyped-url` and matched on
    its host, because whether it starts depends on the client reading it and
    the registration is there either way.

    An entry carrying both a `command` and a `url` is described by whichever
    half identifies this toolkit, since that is the half a report and a plan
    act on. Neither field is discarded before the match.
    """
    if not isinstance(entry, dict):
        return ("malformed", "<entry is not an object>", "", [])
    declared = entry.get("type")
    url = entry.get("url")
    command = entry.get("command")
    if declared in DECLARED_REMOTE:
        return (declared, str(url) if url else "<missing url>", "", [])
    remote_half = url is not None and not runs_our_server(entry)
    if command is not None and not remote_half:
        args = entry_args(entry)
        return ("stdio", " ".join([str(command)] + args), str(command), args)
    if url is not None:
        return ("untyped-url", str(url), "", [])
    return ("malformed", "<neither command nor url>", "", [])


def classify(name, entry):
    """definite / possible / no, from what the entry runs rather than its name."""
    kind, endpoint, command, _ = describe(entry)
    if isinstance(entry, dict) and (runs_our_server(entry) or points_at_hosted(entry)):
        return kind, endpoint, command, "definite"
    # Weak signals only ever produce an unverified report, never a match: the
    # key name is free text and an env block is the user's own.
    named_for_us = name == CANON or name.startswith((CANON + "-", CANON + "_"))
    env = entry.get("env") if isinstance(entry, dict) else None
    tagged = isinstance(env, dict) and bool(set(env) & PIPEFY_ENV)
    if named_for_us or tagged:
        return kind, endpoint, command, "possible"
    return kind, endpoint, command, "no"


def installer_shape(entry):
    """Exactly what install.sh's JSON merge writes, and nothing else.

    Without a receipt this is the only evidence that an entry was the
    installer's work rather than the user's, so it is an equality test on the
    whole value: one key, one command, no args, no env.
    """
    if not isinstance(entry, dict):
        return "other"
    if set(entry) == {"command"} and entry.get("command") == BINARY:
        return "installer"
    return "other"


def scan_env_block(path, keypath, segs, block):
    """Report PIPEFY_* keys in an env block, with the JSON path a remover needs.

    The dotted keypath is for humans; the padded segment list is machine-read,
    because a project directory used as a key contains dots and slashes.
    """
    if not isinstance(block, dict):
        return
    for key in block:
        if key in CRED:
            tier = "credential"
        elif key in CONFIG:
            tier = "config"
        else:
            continue
        padded = (list(segs) + [key] + ["-"] * 6)[:6]
        emit("envkey", path, "%s.%s" % (keypath, key), key, tier, *padded)


MCP_ROWS = []


def walk_servers(path, keypath, segs, servers, scope, projdir):
    if not isinstance(servers, dict):
        return
    for name, entry in servers.items():
        kind, endpoint, command, match = classify(name, entry)
        if match != "no":
            emit("mcp", match, name, scope, projdir, path, kind, endpoint,
                 command, installer_shape(entry))
            MCP_ROWS.append(
                (match, name, scope, projdir, path, kind, endpoint, command)
            )
        if isinstance(entry, dict):
            scan_env_block(
                path,
                "%s.%s.env" % (keypath, name),
                list(segs) + [name, "env"],
                entry.get("env"),
            )


def listed(value, name):
    return isinstance(value, list) and name in value


def scan_settings(path, projdir):
    data = load(path)
    if data is None:
        return
    scan_env_block(path, "env", ["env"], data.get("env"))
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

# --- every JSON client, from the table. A row is all it takes to add one.
scoped = None
for row in CLIENTS:
    if row["format"] != "json":
        continue
    # A missing or unreadable config only costs this file: the state directory
    # below is registered independently of it.
    data = load(row["config"]) or {}
    walk_servers(
        row["config"],
        row["servers"],
        [row["servers"]],
        data.get(row["servers"]),
        row["scope"],
        "-",
    )
    if "scopes" in row["caps"]:
        # Per-project registrations and toggles live in the same file, under
        # the project's own path. Scope resolution is this client's concept,
        # which is why it hangs off the capability and not off an id.
        scoped = row
        projects = data.get("projects")
        if isinstance(projects, dict):
            for pdir, pdata in projects.items():
                if pdir not in project_dirs:
                    project_dirs.append(pdir)
                if not isinstance(pdata, dict):
                    continue
                where = "%s projects.%s" % (row["config"], pdir)
                walk_servers(
                    row["config"],
                    "projects.%s.%s" % (pdir, row["servers"]),
                    ["projects", pdir, row["servers"]],
                    pdata.get(row["servers"]),
                    "local",
                    pdir,
                )
                if listed(pdata.get("disabledMcpjsonServers"), CANON):
                    emit("disabledjson", pdir, where)
                if listed(pdata.get("enabledMcpjsonServers"), CANON):
                    emit("enabledjson", pdir, where)
                if listed(pdata.get("disabledMcpServers"), CANON):
                    emit("disabledsrv", pdir, where)
    if "plugin-system" in row["caps"]:
        usage = data.get("pluginUsage")
        if isinstance(usage, dict) and PLUGIN in usage:
            emit("pluginusage", row["config"], "pluginUsage[%s]" % PLUGIN)

    statedir = row["statedir"]
    if statedir == "-":
        continue

    for name in ("settings.json", "settings.local.json"):
        scan_settings(os.path.join(statedir, name), "-")

    if "plugin-system" not in row["caps"]:
        continue

    known = os.path.join(statedir, "plugins", "known_marketplaces.json")
    data = load(known)
    if isinstance(data, dict) and MARKET in data:
        entry = data[MARKET] if isinstance(data.get(MARKET), dict) else {}
        emit("marketplace", known, MARKET, str(entry.get("installLocation") or ""))

    installed = os.path.join(statedir, "plugins", "installed_plugins.json")
    data = load(installed)
    if data is None:
        continue
    plugins = data.get("plugins")
    if not isinstance(plugins, dict) or PLUGIN not in plugins:
        continue
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
                walk_servers(plugin_mcp, "mcpServers", ["mcpServers"],
                             pdata.get("mcpServers"), "plugin", "-")

# --- project scope: .mcp.json is the cross-client project file; the settings
# beside it belong to the client that resolves scopes.
for pdir in project_dirs:
    mcp_json = os.path.join(pdir, ".mcp.json")
    data = load(mcp_json)
    if data is not None:
        emit("projectfile", pdir, mcp_json)
        walk_servers(mcp_json, "mcpServers", ["mcpServers"],
                     data.get("mcpServers"), "project", pdir)
    if scoped is None:
        continue
    for name in ("settings.json", "settings.local.json"):
        scan_settings(
            os.path.join(pdir, os.path.basename(scoped["statedir"]), name), pdir
        )


# --- where each installed skill came from. `skills add` keeps a lock file
# recording the source of every skill it wrote; that record is the only
# provenance a skill has, since a directory name is not evidence of anything.
#
# Two layouts, both observed. A global install writes the lock inside the agent
# directory; a project install writes it at the base of the project. The store
# is `<base>/.agents/skills` either way, which is why it is derived from the
# base rather than from wherever the lock happens to sit.
SKILL_LOCKS = (os.path.join(".agents", ".skill-lock.json"), "skills-lock.json")
SKILL_STORE = os.path.join(".agents", "skills")


def scan_skill_lock(base, path):
    data = load(path)
    if not isinstance(data, dict):
        return
    skills = data.get("skills")
    if not isinstance(skills, dict):
        return
    store = os.path.join(base, SKILL_STORE)
    for name, meta in skills.items():
        if not isinstance(meta, dict):
            continue
        source = str(meta.get("source") or "")
        source_url = str(meta.get("sourceUrl") or "")
        ours = source in SKILL_SOURCES or source_url in SKILL_SOURCES
        emit("skilllock", path, name, "ours" if ours else "other",
             source or source_url or "?", store)
    # The skills directory a client reads sits beside the base too, and on a
    # project install it is nowhere this scan would otherwise look.
    emit("skillsdir", os.path.join(base, ".claude", "skills"), path)


seen_locks = set()
for base in [os.path.expanduser("~")] + project_dirs:
    for leaf in SKILL_LOCKS:
        lock = os.path.join(base, leaf)
        if lock in seen_locks:
            continue
        seen_locks.add(lock)
        scan_skill_lock(base, lock)

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

# Newline-separated set membership, compared for equality.
list_has() {
    printf '%s' "$1" | awk -v v="$2" '$0 == v { f = 1 } END { exit !f }'
}

scan_receipt() {
    section "Install receipt"
    if [ "$RCPT_UNREADABLE" -eq 1 ]; then
        uninspected "$RECEIPT_FILE exists but could not be read"
        return 0
    fi
    if [ "$RCPT_PRESENT" -eq 0 ]; then
        note "no install receipt at $RECEIPT_FILE"
        print_heuristic_mode
        return 0
    fi
    finding "$RECEIPT_FILE"
    detail "$RCPT_RECORDS install run(s) recorded"
    if [ "$RCPT_PARTIAL" -gt 0 ]; then
        detail "$RCPT_PARTIAL of them stop mid-record, so that install did not finish;"
        detail "what it did record is still used, and a path that no longer exists is skipped"
    fi
    if [ "$RCPT_FUTURE" -gt 0 ]; then
        detail "$RCPT_FUTURE were written by a newer schema than this script reads, and are"
        detail "skipped whole rather than half-read; get a newer uninstall.sh"
    fi
    if [ "$RCPT_BAD" -gt 0 ]; then
        detail "$RCPT_BAD carry no schema this script recognises and are skipped whole"
    fi
    if [ "$RCPT_JUNK" -gt 0 ]; then
        detail "$RCPT_JUNK lines are malformed and were dropped"
    fi
    if [ -n "$RCPT_TAG" ]; then
        detail "release: $(receipt_unescape "$RCPT_TAG")"
    fi
    while IFS= read -r _sr_line; do
        [ -n "$_sr_line" ] || continue
        detail "installed as a uv tool: $(receipt_unescape "$_sr_line")"
    done <<EOF
$RCPT_TOOLS
EOF
    while IFS="$TAB" read -r _sr_client _sr_made; do
        [ -n "${_sr_client:-}" ] || continue
        if [ "$_sr_made" = true ]; then
            detail "created the '$CANONICAL_NAME' registration in the $_sr_client config"
        else
            detail "found a '$CANONICAL_NAME' registration already in the $_sr_client config and left it"
        fi
    done <<EOF
$RCPT_CREATED
EOF
    if [ "$RCPT_UV_OURS" -eq 1 ]; then
        detail "uv was installed by one of those runs. It is still not removed: by now"
        detail "other tools depend on it, and a tool directory is not uv itself."
    fi
    plan_add 8 ours rmpath "$RECEIPT_FILE" - - - - - - \
        "delete the install receipt $RECEIPT_FILE"
    plan_add 8 ours rmdir "$RECEIPT_STATE" - - - - - - \
        "remove $RECEIPT_STATE if it ends up empty"
}

# Permanent, not transitional: every install that predates the receipt has
# none, and one is only written by a version of install.sh that writes one.
print_heuristic_mode() {
    detail "Heuristic mode. Without a receipt this run cannot tell a registration the"
    detail "installer created from one it found already there and left alone, so in a"
    detail "config the installer writes it removes an entry only where the value is"
    detail "exactly the single command the installer writes, and reports the rest for"
    detail "you to judge. uv is never treated as this toolkit's. This is not a"
    detail "migration step: every install made before the receipt existed lands here."
}

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
    scan_uv_tool_dir -
    # A tool directory the caller's environment no longer points at is
    # invisible to `uv tool list`, which is why install.sh records it.
    _seen=""
    while IFS= read -r _ut_line; do
        [ -n "$_ut_line" ] || continue
        _ut_dir=$(receipt_unescape "$_ut_line")
        [ "$_ut_dir" != "${UV_TOOL_DIR:-}" ] || continue
        if list_has "$_seen" "$_ut_dir"; then
            continue
        fi
        _seen="$_seen$_ut_dir$NL"
        if [ ! -d "$_ut_dir" ]; then
            note "the receipt records a tool directory that is gone: $_ut_dir"
            continue
        fi
        detail "from the install receipt: $_ut_dir"
        scan_uv_tool_dir "$_ut_dir"
    done <<EOF
$RCPT_TOOL_DIRS
EOF
    if [ -z "${UV_TOOL_DIR:-}" ] && [ "$RCPT_PRESENT" -eq 0 ]; then
        detail "install.sh --prefix sets UV_TOOL_DIR, and an install that wrote no receipt"
        detail "recorded it nowhere, so a tool under a custom prefix is invisible here"
        detail "unless that prefix is exported"
    fi
}

# One tool directory: "-" for whatever this environment resolves to, an
# absolute path for one the receipt named.
scan_uv_tool_dir() {
    _sud_dir="$1"
    if is_set "$_sud_dir"; then
        _listing=$(UV_TOOL_DIR="$_sud_dir" uv tool list 2>/dev/null) || _listing=""
    else
        _listing=$(uv tool list 2>/dev/null) || _listing=""
    fi
    for _tool in $UV_TOOLS; do
        # `uv tool list` prints "<name> v<version>" per tool with its
        # executables indented under it. Match the first field exactly.
        if printf '%s\n' "$_listing" \
            | awk -v t="$_tool" '$1 == t { f = 1 } END { exit !f }'; then
            if is_set "$_sud_dir"; then
                finding "uv tool installed: $_tool (under $_sud_dir)"
                _sud_desc="uv tool uninstall $_tool, under $_sud_dir"
            else
                finding "uv tool installed: $_tool"
                _sud_desc="uv tool uninstall $_tool"
            fi
            plan_add 6 ours uvtool "$_tool" "$_sud_dir" - - - - - "$_sud_desc"
        elif ! is_set "$_sud_dir"; then
            note "uv tool not installed: $_tool"
        fi
    done
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

# Whether a `url` with no `type` starts is the reader's business, not this
# script's, so the caveat comes from the capability of the client whose file
# the entry sits in rather than from any client id.
report_untyped_url() {
    [ "$1" = "untyped-url" ] || return 0
    _ru_id=$(client_id_reading "$2")
    [ -n "$_ru_id" ] || return 0
    client_has_cap "$(client_row "$_ru_id")" typed-remote || return 0
    detail "no \"type\" key: $_ru_id reads such an entry as stdio and skips the"
    detail "server, so this one is registered but never starts there. It is still"
    detail "a registration and is still removed."
}

scan_registrations() {
    section "MCP registrations"
    detail "matched on what an entry runs: the $SERVER_BINARY command, a known"
    detail "runner invoking it, or the host $HOSTED_HOST. Either half is"
    detail "enough, and a declared transport type is required for neither, since"
    detail "clients disagree about how to read an entry that omits one. The"
    detail "registration key is reported as data, never a matching criterion."
    if [ -z "$PYTHON3" ]; then
        uninspected "JSON client configs not inspected — python3 unavailable"
        detail "affects the Claude Code, Cursor and Claude Desktop configs, the plugin"
        detail "registry, and every project .mcp.json"
        scan_toml_clients
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
            report_untyped_url "$_kind" "$_place"
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
    scan_toml_clients
}

# Entries carrying a weak signal — a name in this toolkit's namespace, or one
# of its environment variables — that do not run anything identifiable.
# Reported for the reader to judge, never claimed as ours.
scan_possible_registrations() {
    while IFS="$TAB" read -r _ _match _name _scope _kind _endpoint _command _count _s1 _s2 _s3; do
        [ "${_match:-}" = "possible" ] || continue
        if kind_is_remote "$_kind"; then
            finding "unverified: '$_name' at $_scope scope is an HTTP registration that is not the documented hosted endpoint"
        else
            finding "unverified: '$_name' at $_scope scope does not run $SERVER_BINARY"
        fi
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

scan_toml_clients() {
    while IFS='|' read -r _tc_id _tc_plat _tc_fmt _tc_cfg _tc_srv _tc_scope _tc_st _tc_caps _tc_cli; do
        [ "${_tc_fmt:-}" = "toml" ] || continue
        scan_toml_client "$_tc_id" "$_tc_cfg" "$_tc_srv"
    done <<EOF
$(client_rows)
EOF
}

# A TOML client's config is text install.sh appends to blind, so detection keys
# on the section header. Every section is then matched on what it runs, so a
# server registered under another name is found too.
scan_toml_client() {
    _tcl_id="$1"
    _tcl_file="$2"
    _tcl_key="$3"
    if [ ! -f "$_tcl_file" ]; then
        note "$_tcl_id: no $_tcl_file"
        return 0
    fi
    _hit=0
    while IFS="$TAB" read -r _name _command _url _args; do
        [ -n "${_name:-}" ] || continue
        # Both halves of the rule, read independently: a section carrying a
        # command and a url matches on either, so neither a local nor a hosted
        # registration hides behind the other field.
        _hosted=0
        if is_set "$_url" && [ "$(url_host "$_url")" = "$HOSTED_HOST" ]; then
            _hosted=1
        fi
        _ours=0
        # Word splitting is how the flattened argument list is re-read.
        # shellcheck disable=SC2086
        if is_set "$_command" && stdio_matches "$_command" $_args; then
            _ours=1
        fi
        [ "$_hosted" -eq 1 ] || [ "$_ours" -eq 1 ] || continue
        _hit=$((_hit + 1))
        # Described by the half that identifies this toolkit.
        if [ "$_ours" -eq 0 ]; then
            finding "$_tcl_id, section [$_tcl_key.$_name]: $_url"
        else
            if is_set "$_args"; then
                finding "$_tcl_id, section [$_tcl_key.$_name]: $_command $_args"
            else
                finding "$_tcl_id, section [$_tcl_key.$_name]: $_command"
            fi
            if ! command -v "$_command" >/dev/null 2>&1; then
                detail "broken: command '$_command' does not resolve on PATH"
            fi
        fi
        detail "in $_tcl_file"
        plan_toml_section "$_tcl_id" "$_tcl_file" "$_tcl_key" "$_name"
    done <<EOF
$(toml_sections "$_tcl_file" "$_tcl_key")
EOF
    if [ "$_hit" -eq 0 ]; then
        note "$_tcl_id: no section in $_tcl_file runs this toolkit"
    fi
}

# One tab-separated line per [<key>.<name>] section: name, command, url, and
# args flattened to a space-separated list.
toml_sections() {
    AW_KEY="$2" awk '
        # "-" for an empty field: tab is IFS whitespace, so the consuming shell
        # would collapse a run of tabs and shift columns.
        function dash(v) { return v == "" ? "-" : v }
        function flush() {
            if (sec != "")
                printf "%s\t%s\t%s\t%s\n", sec, dash(cmd), dash(url), dash(args)
            sec = ""; cmd = ""; url = ""; args = ""
        }
        BEGIN { key = ENVIRON["AW_KEY"]; head = "^\\[" key "\\.[^.]+\\]$" }
        /^[ \t]*\[/ {
            flush()
            if ($0 ~ head) {
                sec = substr($0, length(key) + 3, length($0) - length(key) - 3)
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

# install.sh appends exactly a header and one `command = "<binary>"` line. A
# section holding anything else — extra keys, a sub-table, a comment — was
# written or edited by hand, and is reported rather than excised.
#
# A sub-table counts wherever it sits in the file. `[mcp_servers.<name>.env]` is
# a separate header, so a scan that reads only up to the next `[` never sees it,
# and an excision that stops there leaves it behind holding whatever the hand
# that wrote it put in — a token, most usefully. Treating the parent as
# hand-edited keeps the pair together, reported and intact.
toml_section_is_pristine() {
    AW_KEY="$2" AW_NAME="$3" AW_BIN="$SERVER_BINARY" awk '
        function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
        BEGIN {
            sec = "[" ENVIRON["AW_KEY"] "." ENVIRON["AW_NAME"] "]"
            child = "[" ENVIRON["AW_KEY"] "." ENVIRON["AW_NAME"] "."
            want = "command = \"" ENVIRON["AW_BIN"] "\""
        }
        {
            t = trim($0)
            if (inside && substr(t, 1, 1) == "[") inside = 0
            if (substr(t, 1, length(child)) == child) { other++; next }
            if (inside) {
                if (t == "") next
                if (t == want) { seen++; next }
                other++; next
            }
            if (t == sec) inside = 1
        }
        END { exit !(seen == 1 && other == 0) }
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

# Where the marketplace clone belongs, derived from the client table. The
# registry's own `installLocation` is data this script did not write, so it is
# a claim to check against this, never a deletion target on its own.
marketplace_clone_path() {
    _mcp_row=$(client_row_with_cap plugin-system)
    [ -n "$_mcp_row" ] || return 1
    printf '%s\n' "$(client_field "$_mcp_row" 7)/plugins/marketplaces/$MARKETPLACE_ID"
}

# Is a recorded clone location the canonical clone, or something inside it?
marketplace_clone_confines() {
    [ -n "${1:-}" ] && [ "$1" != "-" ] || return 1
    _mcc_want=$(marketplace_clone_path) || return 1
    _mcc_want=$(canonical_path "$_mcc_want")
    _mcc_have=$(canonical_path "$1")
    case "$_mcc_have" in
        "$_mcc_want"|"$_mcc_want"/*) return 0 ;;
    esac
    return 1
}

scan_plugin() {
    _prow=$(client_row_with_cap plugin-system)
    [ -n "$_prow" ] || return 0
    _pclient=$(client_field "$_prow" 1)
    _pstate=$(client_field "$_prow" 7)
    section "$_pclient plugin and marketplace"
    _clone="$_pstate/plugins/marketplaces/$MARKETPLACE_ID"
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
            if ! marketplace_clone_confines "$_location"; then
                detail "that is outside $_clone, so it is reported and never deleted:"
                detail "this registry is not a file this script wrote, and a path read"
                detail "out of it does not authorise a removal"
            fi
        fi
        case "$_key" in
            extraKnownMarketplaces.*)
                plan_add 5 ours jsonkey "$_file" extraKnownMarketplaces \
                    "$MARKETPLACE_ID" - - - - \
                    "drop extraKnownMarketplaces.$MARKETPLACE_ID from $_file" ;;
            *)
                _mk_desc="unregister the '$MARKETPLACE_ID' marketplace"
                if marketplace_clone_confines "$_location" && [ -d "$_location" ]; then
                    _mk_desc="$_mk_desc, and delete its clone at $_location"
                fi
                plan_add 5 ours market "$MARKETPLACE_ID" "$_file" "$_location" \
                    - - - - "$_mk_desc" ;;
        esac
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
        plan_add 5 ours plugin "$_id" "$_file" "$_scope" - - - - \
            "uninstall the $_id plugin ($_scope scope)"
    done <<EOF
$(records plugin)
EOF
    while IFS="$TAB" read -r _ _file _key _state; do
        [ -n "${_file:-}" ] || continue
        finding "plugin flag: $_key = $_state in $_file"
        plan_add 5 ours jsonkey "$_file" enabledPlugins "$PLUGIN_ID" - - - - \
            "drop enabledPlugins[$PLUGIN_ID] from $_file"
    done <<EOF
$(records pluginflag)
EOF
    while IFS="$TAB" read -r _ _file _key; do
        [ -n "${_file:-}" ] || continue
        finding "plugin usage record: $_key in $_file"
        plan_add 5 ours jsonkey "$_file" pluginUsage "$PLUGIN_ID" - - - - \
            "drop pluginUsage[$PLUGIN_ID] from $_file"
    done <<EOF
$(records pluginusage)
EOF
    if [ -d "$_clone" ]; then
        if [ "$_registered" -eq 0 ]; then
            finding "orphan clone: $_clone exists with no marketplace registration"
            plan_add 5 ours rmpath "$_clone" - - - - - - \
                "delete the orphan marketplace clone $_clone"
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

keychain_has_entry() {
    case "$OS" in
        Darwin)
            command -v security >/dev/null 2>&1 || return 1
            security find-generic-password -s "$KEYCHAIN_SERVICE" >/dev/null 2>&1 ;;
        Linux)
            command -v secret-tool >/dev/null 2>&1 || return 1
            [ -n "$(secret-tool search service "$KEYCHAIN_SERVICE" 2>/dev/null)" ] ;;
        *) return 1 ;;
    esac
}

scan_credentials() {
    section "Stored credentials"
    scan_keychain_backend
    _cfg="$CONFIG_DIR/keyring.cfg"
    # `pipefy auth logout` is the only step that can revoke server-side, so it
    # is planned ahead of every local delete and only when there is a session
    # to revoke.
    if [ "$COLLECTING" -eq 1 ]; then
        if [ -f "$_cfg" ] || keychain_has_entry; then
            plan_add 1 credential logout - - - - - - - \
                "revoke and delete the stored session (pipefy auth logout)"
        fi
    fi
    case "$OS" in
        Darwin) scan_keychain_macos ;;
        Linux) scan_keychain_linux ;;
    esac
    if [ ! -f "$_cfg" ]; then
        note "no file-backend store at $_cfg"
        return 0
    fi
    finding "file keyring backend: $_cfg stores refresh tokens in plaintext"
    plan_add 2 credential rmpath "$_cfg" - - - - - - \
        "delete the plaintext file keyring $_cfg"
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
        plan_add 2 credential keychain "$_acct" - - - - - - \
            "delete the keychain item $KEYCHAIN_SERVICE / $_acct"
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
        # Uninspected, not clean, and the same call as the missing `security`
        # on Darwin: a credential store nothing could read is a source this run
        # has no answer for, whatever the reason it could not read it.
        uninspected "keychain not inspected — 'secret-tool' not on PATH"
        detail "install libsecret-tools (or the Secret Service client for your desktop)"
        detail "to have this run enumerate the store, or check it yourself"
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
        plan_add 2 credential keychain "$_acct" - - - - - - \
            "delete the keychain item $KEYCHAIN_SERVICE / $_acct"
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
        # `pipefy auth logout` recreates it with a refresh.lock, so the cleanup
        # is planned now even though there is nothing here yet.
        if plan_has_kind logout; then
            plan_add 8 ours rmpath "$CONFIG_DIR/refresh.lock" - - - - - - \
                "delete $CONFIG_DIR/refresh.lock, which the logout above recreates"
            plan_add 8 ours rmdir "$CONFIG_DIR" - - - - - - \
                "remove $CONFIG_DIR if it ends up empty"
        fi
        return 0
    fi
    _empty=1
    while IFS= read -r _name; do
        [ -n "$_name" ] || continue
        _empty=0
        case "$_name" in
            config.toml|.env|.env.*)
                finding "$CONFIG_DIR/$_name (user-authored; never remove without consent)"
                plan_add 8 userconfig rmpath "$CONFIG_DIR/$_name" - - - - - - \
                    "delete your $CONFIG_DIR/$_name" ;;
            keyring.cfg)
                note "$CONFIG_DIR/$_name (reported under stored credentials)" ;;
            *.bak.*)
                note "$CONFIG_DIR/$_name (a backup; kept on purpose)" ;;
            refresh.lock)
                finding "$CONFIG_DIR/$_name"
                plan_add 8 ours rmpath "$CONFIG_DIR/$_name" - - - - - - \
                    "delete $CONFIG_DIR/$_name" ;;
            *)
                finding "$CONFIG_DIR/$_name"
                note "$CONFIG_DIR/$_name is not a file this toolkit writes; left in place" ;;
        esac
    done <<EOF
$(ls -A "$CONFIG_DIR" 2>/dev/null)
EOF
    if [ "$_empty" -eq 1 ]; then
        note "exists but is empty"
    fi
    # Last action of the run, and only if nothing of the user's is left in it.
    plan_add 8 ours rmdir "$CONFIG_DIR" - - - - - - \
        "remove $CONFIG_DIR if it ends up empty"
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

is_credential_name() {
    printf '%s\n' "$CRED_ENV_NAMES" | awk -v n="$1" '$0 == n { f = 1 } END { exit !f }'
}

# An assignment to the exact name, optionally exported. The remover deletes
# the lines this expression matches, so detection and removal cannot disagree
# about what counts as an assignment.
rc_assignment_ere() {
    printf '%s\n' "^[[:space:]]*(export[[:space:]]+)?$1="
}

fish_assignment_ere() {
    printf '%s\n' "^[[:space:]]*set([[:space:]]+-[A-Za-z]+)*[[:space:]]+$1[[:space:]]"
}

# Line numbers only, so no value ever reaches the report.
matching_lines() {
    grep -nE "$2" "$1" | cut -d: -f1 | tr '\n' ' '
}

scan_shell_rc() {
    _hit=0
    for _rc in \
        "$HOME/.profile" "$HOME/.bashrc" "$HOME/.bash_profile" "$HOME/.bash_login" \
        "$HOME/.zshenv" "$HOME/.zprofile" "$HOME/.zshrc" "$HOME/.kshrc" \
        "${XDG_CONFIG_HOME:-$HOME/.config}/fish/config.fish"
    do
        [ -f "$_rc" ] || continue
        case "$_rc" in
            */config.fish) _fish=1 ;;
            *) _fish=0 ;;
        esac
        for _name in $CRED_ENV_NAMES $CONFIG_ENV_NAMES; do
            if is_credential_name "$_name"; then
                _class=credential
                _phase=2
            else
                _class=userconfig
                _phase=8
            fi
            if [ "$_fish" -eq 1 ]; then
                _ere=$(fish_assignment_ere "$_name")
            else
                _ere=$(rc_assignment_ere "$_name")
            fi
            _lines=$(matching_lines "$_rc" "$_ere") || _lines=""
            [ -n "$_lines" ] || continue
            _hit=1
            finding "$_name assigned in $_rc (line ${_lines% })"
            plan_add "$_phase" "$_class" rcline "$_rc" "$_ere" - - - - - \
                "delete the $_name assignment from $_rc"
        done
    done
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
    while IFS="$TAB" read -r _ _file _keypath _name _tier _s1 _s2 _s3 _s4 _s5 _s6; do
        [ -n "${_file:-}" ] || continue
        _hit=1
        finding "$_name ($_tier) in $_file at $_keypath"
        if [ "$_tier" = "credential" ]; then
            plan_add 2 credential jsonkey "$_file" \
                "$_s1" "$_s2" "$_s3" "$_s4" "$_s5" "$_s6" \
                "delete $_keypath from $_file"
        else
            plan_add 8 userconfig jsonkey "$_file" \
                "$_s1" "$_s2" "$_s3" "$_s4" "$_s5" "$_s6" \
                "delete $_keypath from $_file"
        fi
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
        plan_add 8 ours rmpath "$_f" - - - - - - "delete $_f"
    done
    if [ -f "$HOME/.bashrc" ]; then
        # A source directive naming our exact script, not a line mentioning it.
        _lines=$(grep -nE '^[[:space:]]*(source|\.)[[:space:]]+.*/\.bash_completions/pipefy\.sh' "$HOME/.bashrc" \
            | cut -d: -f1 | tr '\n' ' ') || _lines=""
        if [ -n "$_lines" ]; then
            _hit=1
            finding "$HOME/.bashrc sources the completion script (line ${_lines% })"
            plan_add 8 userfile rcline "$HOME/.bashrc" \
                '^[[:space:]]*(source|\.)[[:space:]]+.*/\.bash_completions/pipefy\.sh' \
                - - - - - "delete the completion source line from $HOME/.bashrc"
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
    # `npx skills add` picks where it writes, so install.sh records what it
    # observed afterwards. Absent that, the fallback is the state directory of
    # the client that owns the plugin system, which is where it was seen to
    # land.
    _dirs=""
    _srow=$(client_row_with_cap plugin-system)
    if [ -n "$_srow" ]; then
        _dirs="$(client_field "$_srow" 7)/skills$NL"
    fi
    while IFS= read -r _sk_line; do
        [ -n "$_sk_line" ] || continue
        _sk_dir=$(receipt_unescape "$_sk_line")
        if list_has "$_dirs" "$_sk_dir"; then
            continue
        fi
        _dirs="$_dirs$_sk_dir$NL"
    done <<EOF
$RCPT_SKILL_DIRS
EOF
    # A project install links from a skills directory beside the project, which
    # is in no client's row and in no receipt this machine necessarily has.
    while IFS="$TAB" read -r _ _sk_dir _; do
        [ -n "${_sk_dir:-}" ] || continue
        if list_has "$_dirs" "$_sk_dir"; then
            continue
        fi
        _dirs="$_dirs$_sk_dir$NL"
    done <<EOF
$(records skillsdir)
EOF
    if [ -z "$PYTHON3" ]; then
        uninspected "skill provenance not inspected — python3 unavailable"
        detail "the source of an installed skill is recorded in a JSON lock file, and"
        detail "without it this run cannot tell one of ours from one of yours"
    fi
    [ -n "$_dirs" ] || return 0
    while IFS= read -r _dir; do
        [ -n "$_dir" ] || continue
        scan_skills_dir "$_dir"
    done <<EOF
$_dirs
EOF
}

# Where a skill came from, as recorded by the tool that installed it, or by the
# install receipt. Both are records; neither is a guess.
#
# The name prefix is not evidence and is never treated as any. `pipefy-*` is a
# namespace anyone may write in, and a teardown that reads it as ownership
# deletes work it did not create and cannot restore. That is the whole reason
# this function exists rather than a glob.
skill_provenance() {
    while IFS= read -r _sp_line; do
        [ -n "$_sp_line" ] || continue
        [ "$(receipt_unescape "$_sp_line")" = "$1" ] || continue
        printf '%s\n' "receipt"
        return 0
    done <<EOF
$RCPT_SKILLS
EOF
    records skilllock \
        | awk -F"$TAB" -v n="$1" '$3 == n { print $4 "\t" $5; exit }'
}

# The lock file that describes a skill. The path is one the probe built from
# $HOME and the project directories it already sweeps, never a string read out
# of a file, and it is only ever edited as JSON with a backup taken first.
skill_lock_file() {
    records skilllock | awk -F"$TAB" -v n="$1" '$3 == n { print $2; exit }'
}

scan_skills_dir() {
    _sd_dir="$1"
    if [ ! -d "$_sd_dir" ]; then
        note "no $_sd_dir"
        return 0
    fi
    _hit=0
    _theirs=0
    for _skill in "$_sd_dir"/pipefy-*; do
        # A directory holding a SKILL.md, under the name `npx skills add`
        # gives this catalog's skills.
        [ -f "$_skill/SKILL.md" ] || continue
        _sname=$(basename "$_skill")
        _prov=$(skill_provenance "$_sname")
        case "$_prov" in
            receipt|ours*) ;;
            other*)
                _theirs=$((_theirs + 1))
                note "$_sname in $_sd_dir came from $(printf '%s' "$_prov" | cut -f2-), not this toolkit; left alone"
                continue ;;
            *)
                _theirs=$((_theirs + 1))
                note "$_sname in $_sd_dir: nothing records where it came from, so it is left alone"
                detail "the name prefix is not evidence of who wrote it; delete it yourself"
                detail "if it is stale"
                continue ;;
        esac
        _hit=$((_hit + 1))
        detail "$_sname"
        plan_add 7 ours rmpath "$_skill" - - - - - - \
            "delete the $_sname skill"
        plan_skill_store "$_skill" "$_sname"
    done
    if [ "$_hit" -eq 0 ]; then
        note "no pipefy-* skills from this toolkit in $_sd_dir"
    else
        finding "$_hit pipefy-* skills from this toolkit under $_sd_dir"
    fi
    if [ "$_theirs" -gt 0 ]; then
        detail "$_theirs other pipefy-* skill(s) here are not this toolkit's and stay"
    fi
}

# The store `skills add` wrote a skill's content into, as the probe derived it
# from the base its lock file was found at. The lock's own name differs between
# the global and project layouts and its directory differs with it, so the
# store is derived from the base, which does not.
skill_store_dir() {
    records skilllock | awk -F"$TAB" -v n="$1" '$3 == n { print $6; exit }'
}

# Is a link target inside that store? Strictly inside: the store root holds
# every agent's skills, and no single skill is ever the root itself.
skill_store_confines() {
    { [ -n "${2:-}" ] && [ "$2" != "-" ]; } || return 1
    _ssc_root=$(canonical_path "$2")
    _ssc_have=$(canonical_path "$1")
    case "$_ssc_have" in
        "$_ssc_root"/*) return 0 ;;
    esac
    return 1
}

# What the entry in the skills directory points at, and the lock entry that
# describes it. A skill directory is often a link into a shared store, so
# removing only the link leaves the content and the record of it behind, and a
# run that says the skill is gone would be wrong.
#
# Following a link is unbounded reach, so the target is confined the way the
# marketplace clone is: it is deleted only when it sits inside the store the
# lock file names, and a link pointing anywhere else — a checkout of the user's
# own, most likely — costs the link and nothing more. The report says so and
# names what stayed, because "deleted the skill" would otherwise be false.
plan_skill_store() {
    _pss_lock=$(skill_lock_file "$2")
    _pss_store=$(skill_store_dir "$2")
    if [ -L "$1" ]; then
        _pss_target=$(canonical_path "$(resolve_link "$1")")
        if [ -d "$_pss_target" ] && [ "$_pss_target" != "$(canonical_path "$1")" ]; then
            if skill_store_confines "$_pss_target" "$_pss_store"; then
                detail "content at $_pss_target"
                plan_add 7 ours rmpath "$_pss_target" - - - - - - \
                    "delete the $2 skill content at $_pss_target"
            else
                detail "links out to $_pss_target, which is outside the skills store"
                detail "this toolkit's skills are written to; only the link is removed"
                note_left "the $2 entry is a link to $_pss_target, outside the skills store: the link is removed and that directory is left exactly as it is"
            fi
        fi
    fi
    [ -n "$_pss_lock" ] || return 0
    plan_add 7 ours jsonkey "$_pss_lock" skills "$2" - - - - \
        "drop the $2 entry from $_pss_lock"
    # Phase 8, not 7: this only holds once every entry dropped above is gone,
    # and rows inside a phase run in the order they were planned.
    plan_add 8 ours rmlock "$_pss_lock" - - - - - - \
        "remove $_pss_lock if it ends up recording no skills"
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


# ------------------------------------------------------------ plan records
#
# One tab-separated row per action, eleven fields:
#
#   phase class kind a1 a2 a3 a4 a5 a6 a7 description
#
# phase fixes execution order and is load-bearing:
#
#   1 revoke     only `pipefy auth logout` reaches the identity provider, and
#                that ability goes away with the tool environment
#   2 credentials  local credential stores, once revocation has had its chance
#   3 shadowing registrations  a local- or project-scope entry outranks the
#                user-scope one of the same name, and phase 4 has to be able to
#                resolve that name
#   4 hosted token  `<cli> mcp logout <name>` resolves the name across scopes
#                with no way to say which, so it runs after the entries that
#                outrank the hosted one are gone and before the hosted entry
#                itself is. It is a credential and belongs with phase 2 by
#                class; it sits here because it is the only credential whose
#                store is reached through a registration
#   5 client configs  before the tools, so no registration is left pointing at
#                a binary that no longer exists
#   6 tools
#   7 skills
#   8 runtime state  last, because `pipefy auth logout` and `auth status`
#                recreate the config directory
#
# class picks the approval tier and the --keep-* filters:
#
#   ours        tier 1, reversible by re-installing
#   credential  tier 2, cannot be undone; skipped by --keep-credentials
#   userfile    tier 3, the user's file, backed up first
#   userconfig  tier 3, and skipped by --keep-config
#
# kinds and their slots:
#
#   mcpreg      a1 name  a2 scope  a3 project dir  a4 config file
#   mcpdisable  a1 name  a2 project dir
#   jsonkey     a1 file  a2..a7 key path, "-" terminated
#   toml        a1 file  a2 table key  a3 section name
#   plugin      a1 plugin id  a2 registry file  a3 scope
#   market      a1 marketplace id  a2 registry file  a3 clone location
#   uvtool      a1 tool name  a2 UV_TOOL_DIR the receipt named, or "-"
#   logout      -
#   mcplogout   a1 registration name
#   keychain    a1 account
#   rmpath      a1 path
#   rmdir       a1 path, removed only when empty
#   rmlock      a1 skills lock file, removed only when it records no skills
#   rcline      a1 file  a2 extended regular expression matching the lines

plan_add() {
    [ "$COLLECTING" -eq 1 ] || return 0
    case "$2" in
        credential) [ "$KEEP_CREDENTIALS" -eq 0 ] || {
            note_left "${11} — kept by --keep-credentials"
            return 0
        } ;;
        userconfig) [ "$KEEP_CONFIG" -eq 0 ] || {
            note_left "${11} — kept by --keep-config"
            return 0
        } ;;
    esac
    _pa_row=$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
        "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}")
    # The same artifact can be reached from more than one source — a settings
    # file that is also the working directory's project settings, say. One row
    # per action keeps the count honest and the execution idempotent.
    if grep -Fqx -- "$_pa_row" "$PLAN" 2>/dev/null; then
        return 0
    fi
    printf '%s\n' "$_pa_row" >>"$PLAN"
}

# One line per distinct note: the same artifact can be reached from more than
# one source, and saying it twice reads as two problems.
record_note() {
    _nt_row=$(printf '%s\t%s' "$1" "$2")
    if grep -Fqx -- "$_nt_row" "$NOTES" 2>/dev/null; then
        return 0
    fi
    printf '%s\n' "$_nt_row" >>"$NOTES"
}

note_done() { record_note 'done' "$*"; }
note_fail() { record_note fail "$*"; }
note_left() { record_note left "$*"; }
note_manual() { record_note manual "$*"; }
note_unverified() { record_note unverified "$*"; }
note_backup() { record_note backup "$*"; }
notes_of() { awk -F"$TAB" -v k="$1" '$1 == k { print $2 }' "$NOTES"; }

tier_rows() {
    awk -F"$TAB" -v want="$1" '
        { tier = ($2 == "ours") ? 1 : (($2 == "credential") ? 2 : 3) }
        tier == want
    ' "$PLAN"
}

count_lines() { awk 'END { print NR + 0 }' "$1"; }

tier_count() { tier_rows "$1" | awk 'END { print NR + 0 }'; }

phase_rows() { awk -F"$TAB" -v want="$1" '$1 == want' "$PLAN"; }

plan_has_kind() {
    awk -F"$TAB" -v k="$1" '$3 == k { f = 1 } END { exit !f }' "$PLAN"
}

tier_approved() {
    case "$1" in
        ours) [ "$TIER1_OK" -eq 1 ] ;;
        credential) [ "$TIER2_OK" -eq 1 ] ;;
        *) [ "$TIER3_OK" -eq 1 ] ;;
    esac
}

# ---------------------------------------------------------- planning passes

# Registrations are planned from the scan's own records, so removal always uses
# the name an entry was really registered under.
plan_registrations() {
    [ "$COLLECTING" -eq 1 ] || return 0
    [ -n "$PYTHON3" ] || return 0
    _hosted_seen=""
    while IFS="$TAB" read -r _ _match _name _scope _pdir _file _kind _endpoint _command _shape; do
        [ "${_match:-}" = "definite" ] || continue
        _cid=$(client_id_reading "$_file")
        _crow=$(client_row "$_cid")
        _hosted_row=0
        if kind_is_remote "$_kind" \
            && [ "$(url_host "$_endpoint")" = "$HOSTED_HOST" ]; then
            _hosted_row=1
            plan_hosted_token "$_cid" "$_crow" "$_name"
        fi
        # A plugin's own MCP config goes with the plugin, never on its own.
        [ "$_scope" != "plugin" ] || continue
        if ! client_selected "$_cid"; then
            note_left "'$_name' in $_file — --client $CLIENT excludes $_cid"
            continue
        fi
        # A local- or project-scope entry outranks the user-scope one the hosted
        # token belongs to, so it goes in the unshadowing phase — unless it is
        # itself the hosted entry, which has to outlive its own logout.
        if [ "$_hosted_row" -eq 0 ]; then
            _regphase=3
        else
            _regphase=5
        fi
        case "$_scope" in
            user|local)
                [ "$_scope" = local ] || _regphase=5
                plan_add "$_regphase" ours mcpreg "$_name" "$_scope" "$_pdir" "$_file" - - - \
                    "remove the '$_name' registration ($_scope scope) from $_file" ;;
            project)
                plan_project_registration "$_name" "$_pdir" "$_file" "$_regphase" ;;
            *)
                # Every remaining scope is a client whose config install.sh
                # writes itself, so provenance is answerable and is asked.
                registration_is_ours "$_cid" "$_name" "$_shape" "$_file" || continue
                plan_add 5 ours jsonkey "$_file" "$(client_field "$_crow" 5)" \
                    "$_name" - - - - \
                    "remove the '$_name' registration from $_file" ;;
        esac
    done <<EOF
$(records mcp)
EOF
}

# May this run delete a registration from a config install.sh writes?
#
# With a receipt the answer is recorded fact: the installer either created the
# entry or found it already there, and an entry it found is the user's. Without
# one it is a judgement, and the judgement is narrow on purpose — only a value
# that is exactly the single command the installer writes. Every install made
# before the receipt existed takes that path, so it is permanent.
#
# The receipt speaks only for the canonical name, because that is the only name
# install.sh registers under. A definite match under any other name in the same
# file is judged on its shape like any other.
registration_is_ours() {
    _rio_client="$1"
    _rio_name="$2"
    _rio_shape="$3"
    _rio_file="$4"
    if [ "$RCPT_PRESENT" -eq 1 ] && [ "$_rio_name" = "$CANONICAL_NAME" ]; then
        case "$(receipt_entry_created "$_rio_client")" in
            true) return 0 ;;
            false)
                note_left "'$_rio_name' in $_rio_file was already registered when install.sh ran, which recorded leaving it as it found it; remove it yourself if you want it gone"
                return 1 ;;
        esac
    fi
    if [ "$_rio_shape" = installer ]; then
        return 0
    fi
    note_left "'$_rio_name' in $_rio_file is not the single command install.sh writes and no receipt records the installer creating it, so it is left alone; remove it yourself if it is yours"
    return 1
}

# The hosted server's OAuth token lives in the client's own credential store,
# so only a client that ships a removal CLI can clear it from here.
plan_hosted_token() {
    case " $_hosted_seen " in
        *" $3 "*) return 0 ;;
    esac
    _hosted_seen="$_hosted_seen $3"
    if client_has_cap "$2" removal-cli; then
        plan_add 4 credential mcplogout "$3" - - - - - - \
            "clear the stored OAuth token for '$3'"
    else
        note_manual "clear the OAuth token for '$3' in $1 yourself; it has no CLI for it"
    fi
}

# A .mcp.json under version control is the repository's own source. Editing it
# is not durable, so the git-clean remediation is offered instead.
plan_project_registration() {
    if ! command -v git >/dev/null 2>&1; then
        note_left "'$1' in $3 — git is not on PATH, so this run cannot tell whether the file is tracked"
        return 0
    fi
    if git -C "$2" ls-files --error-unmatch .mcp.json >/dev/null 2>&1; then
        plan_add "$4" userfile mcpdisable "$1" "$2" - - - - - \
            "disable '$1' for $2 through disabledMcpjsonServers ($3 is git-tracked)"
        return 0
    fi
    plan_add "$4" ours jsonkey "$3" mcpServers "$1" - - - - \
        "remove the '$1' registration from $3"
}

plan_toml_section() {
    [ "$COLLECTING" -eq 1 ] || return 0
    if ! client_selected "$1"; then
        note_left "[$3.$4] in $2 — --client $CLIENT excludes $1"
        return 0
    fi
    if ! toml_section_is_pristine "$2" "$3" "$4"; then
        note_left "[$3.$4] in $2 holds more than the single line the installer appends, or has a [$3.$4.*] sub-table beside it, so it was edited by hand; excise the section and any sub-table of it yourself"
        return 0
    fi
    # The pristine test above is already the shape test heuristic mode relies
    # on; a receipt can still overrule it, because a section the installer
    # found already there is pristine and is not ours.
    if [ "$RCPT_PRESENT" -eq 1 ] && [ "$4" = "$CANONICAL_NAME" ] \
        && [ "$(receipt_entry_created "$1")" = false ]; then
        note_left "[$3.$4] in $2 was already there when install.sh ran, which recorded leaving it as it found it; excise the section yourself if you want it gone"
        return 0
    fi
    plan_add 5 ours toml "$2" "$3" "$4" - - - - \
        "remove the [$3.$4] section from $2"
}

# ------------------------------------------------------------- presentation

present_plan() {
    _total=$(count_lines "$PLAN")
    say ""
    say "PLAN — $_total actions"
    if [ "$_total" -eq 0 ]; then
        say "  nothing to remove"
        return 0
    fi
    for _t in 1 2 3; do
        _n=$(tier_count "$_t")
        [ "$_n" -gt 0 ] || continue
        say ""
        case "$_t" in
            1) say "[1] Ours, reversible — $_n actions" ;;
            2) say "[2] Credentials — $_n actions (cannot be undone)" ;;
            3) say "[3] Your files — $_n actions (backed up first)" ;;
        esac
        while IFS="$TAB" read -r _ _ _ _ _ _ _ _ _ _ _pd; do
            [ -n "${_pd:-}" ] || continue
            say "    $_pd"
        done <<EOF
$(tier_rows "$_t")
EOF
    done
}

# Tiered, not per action: around twenty individual prompts pushes everyone to
# --yes and loses the safety entirely.
approve_tiers() {
    _n=$(tier_count 1)
    if [ "$_n" -gt 0 ]; then
        if confirm "[1] Remove $_n items this toolkit installed? Reinstalling restores them."; then
            TIER1_OK=1
        else
            say "  tier 1 declined; nothing in it is touched"
        fi
    fi
    _n=$(tier_count 2)
    if [ "$_n" -gt 0 ]; then
        if confirm "[2] Delete $_n stored credentials? This cannot be undone."; then
            TIER2_OK=1
        else
            say "  tier 2 declined; credentials stay where they are"
        fi
    fi
    _n=$(tier_count 3)
    if [ "$_n" -gt 0 ]; then
        if confirm "[3] Edit $_n of your own files? Each is backed up to <file>.bak.$BACKUP_STAMP first."; then
            TIER3_OK=1
        else
            say "  tier 3 declined; your files stay as they are"
        fi
    fi
}

# Exact process names, compared after stripping any directory: a substring
# match on "claude" or "cursor" hits unrelated processes.
LIVE_PROCESS_NAMES="claude Claude Cursor cursor-agent codex Code Codex"

live_server_guard() {
    if ! command -v ps >/dev/null 2>&1; then
        note_left "no 'ps' on PATH, so this run could not check for a running client"
        return 0
    fi
    _live=""
    while IFS= read -r _proc; do
        _proc="${_proc##*/}"
        [ -n "$_proc" ] || continue
        for _want in $LIVE_PROCESS_NAMES "$SERVER_BINARY"; do
            [ "$_proc" = "$_want" ] || continue
            case " $_live " in
                *" $_proc "*) ;;
                *) _live="$_live $_proc" ;;
            esac
        done
    done <<EOF
$(ps -A -o comm= 2>/dev/null || true)
EOF
    [ -n "$_live" ] || return 0
    say ""
    say "Running client detected:${_live}"
    say "  A running client rewrites its own config and can put back an entry this"
    say "  run removes. Quit it first, then continue."
    if [ "$YES" -eq 1 ]; then
        warn "--yes given; continuing with${_live} still running"
        note_left "these were running during the run and may have rewritten their config:${_live}"
        return 0
    fi
    confirm "Quit those, then continue?" || abort "Nothing was removed."
}

abort() {
    say ""
    say "$*"
    exit 1
}

# ------------------------------------------------------- removal primitives

# An absolute path with every `.`, `..` and symlink resolved. `realpath` is not
# POSIX and is missing on older macOS, and `realpath -e` would be wrong anyway
# because the path is often one this run is about to create or has just
# emptied.
#
# Two passes. The first cancels `.` and `..` as text, which works whether or not
# the path exists; the second hands the surviving directory to the shell, which
# is the only thing here that can see through a symlink. The final segment is
# left unresolved on purpose: a symlink is deleted as a link, so the link's own
# path is what the guard has to judge.
canonical_path() {
    _cp="$1"
    case "$_cp" in
        /*) ;;
        *) _cp="$PWD/$_cp" ;;
    esac
    _cp_out=""
    _cp_rest="${_cp#/}"
    while [ -n "$_cp_rest" ]; do
        _cp_seg="${_cp_rest%%/*}"
        case "$_cp_rest" in
            */*) _cp_rest="${_cp_rest#*/}" ;;
            *) _cp_rest="" ;;
        esac
        case "$_cp_seg" in
            ''|.) ;;
            ..) _cp_out="${_cp_out%/*}" ;;
            *) _cp_out="$_cp_out/$_cp_seg" ;;
        esac
    done
    if [ -z "$_cp_out" ]; then
        printf '%s\n' "/"
        return 0
    fi
    _cp_base="${_cp_out##*/}"
    _cp_dir="${_cp_out%/*}"
    [ -n "$_cp_dir" ] || _cp_dir=/
    if [ -d "$_cp_dir" ]; then
        _cp_dir=$( ( CDPATH=''; cd -P -- "$_cp_dir" 2>/dev/null && pwd -P ) \
            || printf '%s' "$_cp_dir")
    fi
    case "$_cp_dir" in
        /) printf '%s\n' "/$_cp_base" ;;
        *) printf '%s\n' "$_cp_dir/$_cp_base" ;;
    esac
}

# The one path this script deletes through. Everything routes here so the
# refusals cannot be skipped by a caller that forgot them. Tempfiles this
# script creates come back through here too.
remove_path() {
    _rp="${1:-}"
    _rp_mode="${2:-tree}"
    [ -n "$_rp" ] || err "refusing to remove an empty path"
    case "$_rp" in
        /*) ;;
        *) err "refusing to remove a relative path: $_rp" ;;
    esac
    # Resolved before it is judged: `$HOME/..` is neither the string "/" nor the
    # string "$HOME" and names the directory holding every user account. A guard
    # that compares text is not a guard.
    _rp=$(canonical_path "$_rp")
    _rp_home=$(canonical_path "$HOME")
    [ "$_rp" != "/" ] || err "refusing to remove /"
    [ "$_rp" != "$_rp_home" ] || err "refusing to remove \$HOME ($HOME)"
    case "$_rp_home" in
        "$_rp"/*) err "refusing to remove $_rp: it contains \$HOME ($HOME)" ;;
    esac
    if [ "$_rp_mode" = "empty-dir" ]; then
        run rmdir "$_rp"
    elif [ -e "$_rp" ] || [ -L "$_rp" ]; then
        run rm -rf -- "$_rp"
    fi
}

# Nothing this script did not write is edited before a copy exists beside it.
backup_file() {
    _bk="$1"
    [ -f "$_bk" ] || return 0
    _bk_dest="$_bk.bak.$BACKUP_STAMP"
    if [ -e "$_bk_dest" ]; then
        return 0
    fi
    if run cp -p "$_bk" "$_bk_dest"; then
        BACKUPS=$((BACKUPS + 1))
        note_backup "$_bk_dest"
        return 0
    fi
    warn "could not back up $_bk; leaving it untouched"
    return 1
}

# Rewrite a file through an awk program without ever leaving it half-written:
# the temp file inherits the original's mode from cp -p, and the rename is
# within the same directory, so a reader sees the old file or the new one.
atomic_awk_rewrite() {
    _aw_file="$1"
    _aw_prog="$2"
    _aw_arg="$3"
    _aw_arg2="${4:-}"
    trace "rewrite $_aw_file"
    if [ "$DRY_RUN" -eq 1 ]; then
        return 0
    fi
    _aw_tmp=$(mktemp "$(dirname "$_aw_file")/.pipefy-uninstall.XXXXXX") || return 1
    if cp -p "$_aw_file" "$_aw_tmp" \
        && AW_ARG="$_aw_arg" AW_ARG2="$_aw_arg2" awk "$_aw_prog" "$_aw_file" >"$_aw_tmp" \
        && mv -f "$_aw_tmp" "$_aw_file"
    then
        return 0
    fi
    remove_path "$_aw_tmp"
    return 1
}

# Exit 3 from the program below means the key was already gone, which reaches
# the same end state as removing it.
json_remove_key() {
    _jr_file="$1"
    shift
    [ -n "$PYTHON3" ] || return 1
    trace "remove $* from $_jr_file"
    if [ "$DRY_RUN" -eq 1 ]; then
        return 0
    fi
    _jr_rc=0
    "$PYTHON3" - "$_jr_file" "$@" <<'PY' || _jr_rc=$?
import json
import os
import sys
import tempfile

path = sys.argv[1]
keys = sys.argv[2:]
try:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, ValueError) as exc:
    sys.stderr.write("error: %s: %s\n" % (path, exc))
    sys.exit(1)
node = data
for key in keys[:-1]:
    if not isinstance(node, dict) or key not in node:
        sys.exit(3)
    node = node[key]
if not isinstance(node, dict) or keys[-1] not in node:
    sys.exit(3)
del node[keys[-1]]
fd, tmp = tempfile.mkstemp(
    prefix=os.path.basename(path) + ".", dir=os.path.dirname(path) or "."
)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        # ensure_ascii=False: another server's UTF-8 value is not this run's to
        # rewrite into escapes.
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
except BaseException:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    raise
PY
    [ "$_jr_rc" -ne 3 ] || return 0
    return "$_jr_rc"
}

json_add_disabled() {
    [ -n "$PYTHON3" ] || return 1
    trace "add $3 to projects.$2.disabledMcpjsonServers in $1"
    if [ "$DRY_RUN" -eq 1 ]; then
        return 0
    fi
    _ja_rc=0
    "$PYTHON3" - "$1" "$2" "$3" <<'PY' || _ja_rc=$?
import json
import os
import sys
import tempfile

path, projdir, name = sys.argv[1], sys.argv[2], sys.argv[3]
data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        sys.stderr.write("error: %s: %s\n" % (path, exc))
        sys.exit(1)
if not isinstance(data, dict):
    sys.exit(1)
projects = data.setdefault("projects", {})
if not isinstance(projects, dict):
    sys.exit(1)
entry = projects.setdefault(projdir, {})
if not isinstance(entry, dict):
    sys.exit(1)
disabled = entry.setdefault("disabledMcpjsonServers", [])
if not isinstance(disabled, list):
    sys.exit(1)
if name in disabled:
    sys.exit(3)
disabled.append(name)
fd, tmp = tempfile.mkstemp(
    prefix=os.path.basename(path) + ".", dir=os.path.dirname(path) or "."
)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        # ensure_ascii=False: another server's UTF-8 value is not this run's to
        # rewrite into escapes.
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
except BaseException:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    raise
PY
    [ "$_ja_rc" -ne 3 ] || return 0
    return "$_ja_rc"
}

# A verb is probed for, never inferred from a client version.
cli_verb_exists() {
    _cv_cli="$1"
    _cv_verb="$2"
    shift 2
    [ "$_cv_cli" != "-" ] || return 1
    command -v "$_cv_cli" >/dev/null 2>&1 || return 1
    "$_cv_cli" "$@" --help 2>/dev/null \
        | awk -v v="$_cv_verb" '$1 == v { f = 1 } END { exit !f }'
}

client_row_for_config() {
    client_rows | awk -F'|' -v f="$1" '$4 == f && !seen { print; seen = 1 }'
}

removal_cli() {
    _rc_row=$(client_row_with_cap removal-cli)
    [ -n "$_rc_row" ] || return 1
    _rc_cli=$(client_field "$_rc_row" 9)
    [ "$_rc_cli" != "-" ] || return 1
    printf '%s\n' "$_rc_cli"
}

# ----------------------------------------------------------------- actions

act_mcpreg() {
    _mr_row=$(client_row_for_config "$4")
    _mr_cli=$(client_field "$_mr_row" 9)
    if client_has_cap "$_mr_row" removal-cli && cli_verb_exists "$_mr_cli" remove mcp; then
        if [ "$2" = "local" ]; then
            # Local scope is resolved against the working directory.
            ( cd "$3" && run "$_mr_cli" mcp remove "$1" -s local )
            return $?
        fi
        run "$_mr_cli" mcp remove "$1" -s "$2"
        return $?
    fi
    backup_file "$4" || return 1
    _mr_key=$(client_field "$_mr_row" 5)
    if [ "$2" = "local" ]; then
        json_remove_key "$4" projects "$3" "$_mr_key" "$1"
    else
        json_remove_key "$4" "$_mr_key" "$1"
    fi
}

act_mcpdisable() {
    _md_row=$(client_row_with_cap scopes)
    _md_file=$(client_field "$_md_row" 4)
    backup_file "$_md_file" || return 1
    json_add_disabled "$_md_file" "$2" "$1"
}

act_jsonkey() {
    _jk_file="$1"
    shift
    backup_file "$_jk_file" || return 1
    _jk_n=0
    for _jk_seg in "$@"; do
        [ "$_jk_seg" != "-" ] || break
        _jk_n=$((_jk_n + 1))
    done
    case "$_jk_n" in
        0) return 1 ;;
        1) json_remove_key "$_jk_file" "$1" ;;
        2) json_remove_key "$_jk_file" "$1" "$2" ;;
        3) json_remove_key "$_jk_file" "$1" "$2" "$3" ;;
        4) json_remove_key "$_jk_file" "$1" "$2" "$3" "$4" ;;
        5) json_remove_key "$_jk_file" "$1" "$2" "$3" "$4" "$5" ;;
        *) json_remove_key "$_jk_file" "$1" "$2" "$3" "$4" "$5" "$6" ;;
    esac
}

# Section-aware, because install.sh appends the block as raw text: the excision
# runs from the header to the next table header or end of file. Blank lines are
# held back and printed before the next real line, so the blank the installer
# put in front of its block disappears with it when the block ended the file,
# and a separator between two sections that stay survives.
act_toml() {
    backup_file "$1" || return 1
    # shellcheck disable=SC2016  # an awk program, not a shell expansion
    atomic_awk_rewrite "$1" '
        function trim(s) { sub(/^[ \t]+/, "", s); sub(/[ \t]+$/, "", s); return s }
        BEGIN { sec = "[" ENVIRON["AW_ARG2"] "." ENVIRON["AW_ARG"] "]" }
        {
            t = trim($0)
            if (skip) {
                if (substr(t, 1, 1) == "[") { skip = 0 }
                else { next }
            }
            if (t == sec) { skip = 1; next }
            if (t == "") { pending++; next }
            while (pending > 0) { print ""; pending-- }
            print
        }
    ' "$3" "$2"
}

act_rcline() {
    backup_file "$1" || return 1
    # shellcheck disable=SC2016  # an awk program, not a shell expansion
    atomic_awk_rewrite "$1" '
        BEGIN { re = ENVIRON["AW_ARG"] }
        $0 ~ re { next }
        { print }
    ' "$2"
}

act_rmpath() {
    if [ ! -e "$1" ] && [ ! -L "$1" ]; then
        return 3
    fi
    case "$2" in
        userfile|userconfig) backup_file "$1" || return 1 ;;
    esac
    remove_path "$1"
}

act_rmdir() {
    if [ ! -d "$1" ]; then
        return 0
    fi
    # shellcheck disable=SC2012  # names only, for a message
    _rd_rest=$(ls -A "$1" 2>/dev/null | tr '\n' ' ')
    if [ -n "$_rd_rest" ]; then
        note_left "$1 was kept: it still holds ${_rd_rest% }"
        return 3
    fi
    remove_path "$1" empty-dir
}

# The lock file is `skills add`'s own and can list skills from several sources,
# so it goes only once the entries dropped above were the only ones in it — the
# same contract as rmdir. A project install writes one per project and this is
# the only thing that clears it; the global one usually survives, and should.
act_rmlock() {
    [ -f "$1" ] || return 0
    if [ "$DRY_RUN" -eq 1 ]; then
        trace "remove $1 if it records no skills"
        return 0
    fi
    [ -n "$PYTHON3" ] || return 1
    _rl_rc=0
    "$PYTHON3" - "$1" <<'PY' || _rl_rc=$?
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        data = json.load(fh)
except (OSError, ValueError) as exc:
    sys.stderr.write("error: %s: %s\n" % (sys.argv[1], exc))
    sys.exit(1)
skills = data.get("skills") if isinstance(data, dict) else None
sys.exit(0 if isinstance(skills, dict) and not skills else 3)
PY
    if [ "$_rl_rc" -eq 3 ]; then
        note_left "$1 was kept: it still records skills from another source"
        return 3
    fi
    [ "$_rl_rc" -eq 0 ] || return "$_rl_rc"
    remove_path "$1"
}

act_uvtool() {
    if ! command -v uv >/dev/null 2>&1; then
        note_left "uv is not on PATH, so '$1' could not be uninstalled"
        return 1
    fi
    # A subshell so the tool directory the receipt named applies to this one
    # uninstall and not to any later action.
    if is_set "${2:-}"; then
        ( UV_TOOL_DIR="$2"; export UV_TOOL_DIR; run uv tool uninstall "$1" )
        return $?
    fi
    run uv tool uninstall "$1"
}

act_logout() {
    if ! command -v pipefy >/dev/null 2>&1; then
        note_left "'pipefy' is not on PATH, so the refresh token could not be revoked at the identity provider; whatever is deleted locally stays valid there until it expires"
        return 3
    fi
    if run pipefy auth logout; then
        REVOKED=1
        return 0
    fi
    note_left "'pipefy auth logout' failed, so the refresh token was not revoked at the identity provider; anything deleted locally stays valid until it expires"
    return 1
}

act_keychain() {
    case "$OS" in
        Darwin)
            command -v security >/dev/null 2>&1 || return 1
            run security delete-generic-password -s "$KEYCHAIN_SERVICE" -a "$1" ;;
        Linux)
            command -v secret-tool >/dev/null 2>&1 || return 1
            run secret-tool clear service "$KEYCHAIN_SERVICE" username "$1" ;;
        *) return 1 ;;
    esac
}

act_mcplogout() {
    _ml_cli=$(removal_cli) || _ml_cli="-"
    if cli_verb_exists "$_ml_cli" logout mcp; then
        # 4, not 0: the client's OAuth store is not readable from here, so the
        # only thing this run can observe is that the verb was invoked. The
        # re-scan cannot contradict a silent no-op, and an exit status is not
        # proof of a deleted credential — the rule the local credential path
        # already follows.
        run "$_ml_cli" mcp logout "$1" && return 4
        # The verb resolves the name across scopes and takes no scope flag, so
        # it can bind to an entry other than the one the token belongs to and
        # refuse. Reported as a failure rather than smoothed over.
        note_manual "'$_ml_cli mcp logout $1' failed, so the hosted token is still stored; run /mcp, pick '$1', then Clear authentication"
        return 1
    fi
    note_manual "clear the hosted token by hand: run /mcp, pick '$1', then Clear authentication"
    return 3
}

act_plugin() {
    _pl_cli=$(removal_cli) || _pl_cli="-"
    if cli_verb_exists "$_pl_cli" uninstall plugin; then
        case "$3" in
            user|project|local) run "$_pl_cli" plugin uninstall "$1" -y -s "$3" ;;
            *) run "$_pl_cli" plugin uninstall "$1" -y ;;
        esac
        return $?
    fi
    backup_file "$2" || return 1
    json_remove_key "$2" plugins "$1"
}

act_market() {
    _mk_cli=$(removal_cli) || _mk_cli="-"
    note_left "the '$1' marketplace can come back: a later session re-adds it from a settings file that still lists it or from a plugin that still needs it, so confirm with a fresh session"
    if cli_verb_exists "$_mk_cli" remove "plugin marketplace"; then
        run "$_mk_cli" plugin marketplace remove "$1"
        return $?
    fi
    backup_file "$2" || return 1
    json_remove_key "$2" "$1" || return 1
    [ "$3" != "-" ] || return 0
    if ! marketplace_clone_confines "$3"; then
        note_left "the '$1' registry names $3 as its clone, which is outside $(marketplace_clone_path); it was not removed"
        return 0
    fi
    if [ -d "$3" ]; then
        remove_path "$3"
    fi
}

do_action() {
    _ac_class="$1"
    _ac_kind="$2"
    shift 2
    case "$_ac_kind" in
        mcpreg) act_mcpreg "$1" "$2" "$3" "$4" ;;
        mcpdisable) act_mcpdisable "$1" "$2" ;;
        jsonkey) act_jsonkey "$1" "$2" "$3" "$4" "$5" "$6" "$7" ;;
        toml) act_toml "$1" "$2" "$3" ;;
        plugin) act_plugin "$1" "$2" "$3" ;;
        market) act_market "$1" "$2" "$3" ;;
        uvtool) act_uvtool "$1" "$2" ;;
        logout) act_logout ;;
        mcplogout) act_mcplogout "$1" ;;
        keychain) act_keychain "$1" ;;
        rmpath) act_rmpath "$1" "$_ac_class" ;;
        rmdir) act_rmdir "$1" ;;
        rmlock) act_rmlock "$1" ;;
        rcline) act_rcline "$1" "$2" ;;
        *) return 1 ;;
    esac
}

execute_plan() {
    for _ph in 1 2 3 4 5 6 7 8; do
        while IFS="$TAB" read -r _ _cls _knd _p1 _p2 _p3 _p4 _p5 _p6 _p7 _dsc; do
            [ -n "${_knd:-}" ] || continue
            tier_approved "$_cls" || continue
            _rc=0
            do_action "$_cls" "$_knd" \
                "$_p1" "$_p2" "$_p3" "$_p4" "$_p5" "$_p6" "$_p7" || _rc=$?
            # 3 means the action decided there was nothing to do and said why
            # in a note of its own; 4 means it ran but the result is not
            # observable from here; anything else non-zero is a failure.
            if [ "$_rc" -eq 0 ]; then
                DONE_COUNT=$((DONE_COUNT + 1))
                note_done "$_dsc"
                if [ "$_cls" = credential ] && [ "$_knd" != logout ]; then
                    CRED_DELETED=1
                fi
            elif [ "$_rc" -eq 3 ]; then
                SKIP_COUNT=$((SKIP_COUNT + 1))
            elif [ "$_rc" -eq 4 ]; then
                # Not counted as done and not a credential this run can claim
                # to have deleted: "Removed:" is a verified word.
                UNVERIFIED=$((UNVERIFIED + 1))
                note_unverified "$_dsc"
            else
                FAIL_COUNT=$((FAIL_COUNT + 1))
                note_fail "$_dsc"
            fi
        done <<EOF
$(phase_rows "$_ph")
EOF
    done
}

# ------------------------------------------------------------------ reports

print_scan_next_steps() {
    say ""
    say "This run only reported state — --scan removes nothing."
    say "Nothing on this machine was changed."
    say ""
    say "Run uninstall.sh with no flags to remove what this found, or reverse the"
    say "pieces by hand:"
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

print_note_group() {
    _ng_any=0
    while IFS= read -r _ng_line; do
        [ -n "$_ng_line" ] || continue
        if [ "$_ng_any" -eq 0 ]; then
            say ""
            say "$2"
            _ng_any=1
        fi
        say "  * $_ng_line"
    done <<EOF
$(notes_of "$1")
EOF
}

print_teardown_report() {
    section "What happened"
    say "  $DONE_COUNT completed, $UNVERIFIED unverifiable, $SKIP_COUNT skipped, $FAIL_COUNT failed, $BACKUPS backed up"
    print_note_group 'done' "Removed:"
    print_note_group 'unverified' "Asked for, result not observable from here:"
    if [ "$UNVERIFIED" -gt 0 ]; then
        say "    The store these live in is the client's own and is not readable here, so"
        say "    the command exiting 0 is the only signal and it is not proof: a no-op"
        say "    exits 0 too, and the re-scan cannot tell the two apart. Treat them as"
        say "    still stored until you have checked: run /mcp, pick the server, and"
        say "    read its authentication state."
    fi
    print_note_group 'fail' "Failed — these are still here:"
    print_note_group 'backup' "Backed up before editing:"
    print_note_group 'left' "Left alone:"
    print_note_group 'manual' "Do this yourself:"

    if [ "$CRED_DELETED" -eq 1 ] && [ "$REVOKED" -eq 0 ]; then
        say ""
        say "A credential was deleted from this machine but not revoked at the identity"
        say "provider, so it stays valid there until it expires. Only 'pipefy auth logout'"
        say "revokes, and it could not run here."
    fi

    _live=0
    for _name in $CRED_ENV_NAMES $CONFIG_ENV_NAMES; do
        env_is_set "$_name" || continue
        if [ "$_live" -eq 0 ]; then
            say ""
            say "Set in the shell that started this run:"
            _live=1
        fi
        say "  * unset $_name"
    done
    if [ "$_live" -eq 1 ]; then
        say "  A child process cannot unset a variable in its parent shell. Run the"
        say "  commands above, or start a new shell."
    fi

    say ""
    say "Never touched, by design:"
    say "  * uv itself, and the PATH lines its installer added to your shell rc."
    say "    By now other tools depend on it. Edit those lines yourself if you want"
    say "    them gone: uv tool dir is separate from uv."
    say "  * The uv cache. Never run a bare 'uv cache clean': with no package"
    say "    argument it clears the cache for every package, and uv hardlinks tool"
    say "    environments into it, so a running MCP server breaks until its client"
    say "    restarts. 'uv cache prune' is the safe form, and only while nothing is"
    say "    running."
    say "  * Editable-install entries in the uv cache. They belong to other"
    say "    repositories' virtualenvs and removing one breaks that checkout."
    say "  * Any git-tracked .mcp.json. git restores it on the next checkout, so"
    say "    disabledMcpjsonServers is the durable answer."
    say "  * Your git checkouts. Uninstalling is about tooling, not source."

    say ""
    say "Switching to another channel:"
    say "  hosted        claude mcp add --transport http --scope user \\"
    say "                  --client-id pipefy-mcp $CANONICAL_NAME https://$HOSTED_HOST/mcp"
    say "  plugin        /plugin marketplace add $REPO"
    say "                /plugin install $CANONICAL_NAME"
    say "  local install curl -fsSL https://raw.githubusercontent.com/$REPO/main/install.sh \\"
    say "                  | sh -s -- --client <claude-code|claude-desktop|cursor|codex>"
    if [ -d "$CONFIG_DIR" ]; then
        say ""
        say "$CONFIG_DIR is still here. Any later 'pipefy' invocation recreates it —"
        say "'auth logout' and 'auth status' both do — so its presence is not a failed"
        say "removal."
    fi
}

# ------------------------------------------------------------------ driving

run_scan() {
    FINDINGS=0
    SCAN_ERRORS=0
    : >"$RECORDS"
    read_receipt

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

    # First, because everything downstream is read differently depending on
    # whether there is a receipt, and the reader deserves to know which.
    scan_receipt
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
}

main() {
    parse_args "$@"
    refuse_root
    detect_platform
    resolve_config_dir
    PYTHON3=$(command -v python3 2>/dev/null) || PYTHON3=""
    BACKUP_STAMP=$(date +%Y%m%d%H%M%S 2>/dev/null) || BACKUP_STAMP=""
    [ -n "$BACKUP_STAMP" ] || BACKUP_STAMP="backup"

    resolve_receipt_path
    RECORDS=$(mktemp "${TMPDIR:-/tmp}/pipefy-scan.XXXXXX") \
        || err "mktemp failed (TMPDIR=${TMPDIR:-/tmp})"
    PLAN=$(mktemp "${TMPDIR:-/tmp}/pipefy-plan.XXXXXX") \
        || err "mktemp failed (TMPDIR=${TMPDIR:-/tmp})"
    NOTES=$(mktemp "${TMPDIR:-/tmp}/pipefy-notes.XXXXXX") \
        || err "mktemp failed (TMPDIR=${TMPDIR:-/tmp})"
    trap 'rm -f "$RECORDS" "$PLAN" "$NOTES"' EXIT INT TERM

    if [ "$MODE" = scan ]; then
        say "Pipefy toolkit scan"
    else
        say "Pipefy toolkit uninstall"
    fi
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
    if [ "$DRY_RUN" -eq 1 ] && [ "$MODE" = scan ]; then
        say "  --dry-run has no effect in --scan mode: a scan changes nothing."
    fi

    [ "$MODE" = scan ] || COLLECTING=1
    run_scan

    if [ "$MODE" = scan ]; then
        print_scan_next_steps
        if [ "$SCAN_ERRORS" -gt 0 ]; then
            exit 2
        fi
        if [ "$FINDINGS" -gt 0 ]; then
            exit 1
        fi
        exit 0
    fi

    plan_registrations
    COLLECTING=0

    if [ -z "$PYTHON3" ]; then
        err "removal needs python3: without it the JSON sources above were never read, and a teardown planned from a partial scan would leave exactly the state that causes conflicts. Install python3, or use --scan."
    fi

    present_plan
    if [ "$(count_lines "$PLAN")" -eq 0 ]; then
        say ""
        say "Nothing to remove."
        # An empty plan is not a clean machine: a hand-edited Codex section, a
        # registration the receipt says was already there, a --keep-* filter —
        # each leaves a finding this run deliberately will not touch. The same
        # tree under --scan exits 1, and automation reading exit 0 as clean has
        # to be wrong in only one of the two.
        print_note_group left "Left alone:"
        print_note_group manual "Do this yourself:"
        if [ "$SCAN_ERRORS" -gt 0 ]; then
            exit 2
        fi
        if [ "$FINDINGS" -gt 0 ]; then
            exit 1
        fi
        exit 0
    fi
    if [ "$DRY_RUN" -eq 1 ]; then
        say ""
        say "--dry-run: nothing was changed."
        exit 0
    fi
    if [ "$SCAN_ERRORS" -gt 0 ]; then
        say ""
        say "$SCAN_ERRORS sources could not be inspected, so this plan may be incomplete."
        confirm "Continue anyway?" || abort "Nothing was removed."
    fi

    approve_tiers
    if [ "$TIER1_OK" -eq 0 ] && [ "$TIER2_OK" -eq 0 ] && [ "$TIER3_OK" -eq 0 ]; then
        abort "Every tier was declined. Nothing was removed."
    fi

    live_server_guard
    execute_plan

    section "Re-scan"
    say "  'uninstalled' has to be an observed fact: a uv tool uninstall can succeed"
    say "  while a binary of the same name is still earlier on PATH."
    run_scan
    print_teardown_report

    if [ "$FAIL_COUNT" -gt 0 ] || [ "$SCAN_ERRORS" -gt 0 ]; then
        exit 2
    fi
    # An action whose result this run cannot observe leaves the machine in a
    # state it cannot call clean, so the exit says findings remain rather than
    # success. Otherwise a hosted teardown would report 0 on the strength of a
    # command that may have done nothing at all.
    if [ "$FINDINGS" -gt 0 ] || [ "$UNVERIFIED" -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main "$@"
