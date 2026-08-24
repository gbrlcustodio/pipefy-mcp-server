"""Failure contracts for the Cursor plugin packaging linter."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "scripts"
    / "lint_cursor_plugin.py"
)
_spec = importlib.util.spec_from_file_location("lint_cursor_plugin", _SCRIPT)
assert _spec and _spec.loader
_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_lint)

_SKILL = "skills/onboarding/pipefy-toolkit-setup"
_SKILL_MD = f"{_SKILL}/SKILL.md"
_HOSTED_MCP = {
    "mcpServers": {
        "pipefy": {
            "url": "https://mcp.pipefy.com/mcp",
            "auth": {"CLIENT_ID": "pipefy-mcp"},
        }
    }
}
_SENTINEL = "SENTINEL_NOT_A_REAL_SECRET_9471"


def _assert_redacted_field_failure(errors, field_token):
    assert errors, "expected the lint to fail"
    blob = "\n".join(errors)
    assert field_token in blob, errors
    assert _SENTINEL not in blob, errors


def _write_plugin(
    root,
    *,
    skills=None,
    mcp=None,
    name="pipefy",
    manifest_update=None,
    omit=(),
):
    (root / ".cursor-plugin").mkdir()
    (root / "assets").mkdir()
    (root / "assets" / "logo.svg").write_text("<svg/>", encoding="utf-8")
    skill_dir = root / _SKILL
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    body = {
        "name": name,
        "displayName": "Pipefy",
        "logo": "assets/logo.svg",
        "skills": skills if skills is not None else [f"./{_SKILL}"],
        "commands": [],
        "mcpServers": "./.mcp.json",
    }
    if manifest_update:
        body.update(manifest_update)
    for key in omit:
        body.pop(key, None)
    (root / ".cursor-plugin" / "plugin.json").write_text(
        json.dumps(body),
        encoding="utf-8",
    )
    (root / ".cursor-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "pipefy",
                "owner": {"name": "Pipefy"},
                "plugins": [{"name": "pipefy", "source": "./"}],
            }
        ),
        encoding="utf-8",
    )
    (root / ".mcp.json").write_text(
        json.dumps(mcp if mcp is not None else _HOSTED_MCP),
        encoding="utf-8",
    )


def test_aligned_tree_passes(tmp_path):
    _write_plugin(tmp_path)
    assert _lint.collect_errors(tmp_path, [_SKILL_MD]) == []


def test_unlisted_skill_is_named(tmp_path):
    extra = "skills/observability/pipefy-observability"
    _write_plugin(tmp_path)
    extra_dir = tmp_path / extra
    extra_dir.mkdir(parents=True)
    (extra_dir / "SKILL.md").write_text("# extra\n", encoding="utf-8")
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD, f"{extra}/SKILL.md"])
    assert any(extra in err and "missing" in err for err in errors), errors


def test_stale_manifest_entry_is_named(tmp_path):
    stale = "skills/does-not-exist/fake-skill"
    _write_plugin(tmp_path, skills=[f"./{_SKILL}", f"./{stale}"])
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any(
        stale in err and "which is not a tracked skill" in err for err in errors
    ), errors


def test_mcp_command_key_is_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                    "command": "pipefy-mcp-server",
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("unexpected key 'command'" in err for err in errors), errors


def test_placeholder_is_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                    "headers": {"Authorization": "Bearer ${API_TOKEN}"},
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    # Pin the placeholder rule itself, not just the substring: the fixture also
    # trips the server allowlist, and asserting on the token alone would let
    # this test pass with the placeholder rule deleted.
    assert any("contains placeholder" in err for err in errors), errors
    assert any("${API_TOKEN}" in err for err in errors), errors


def test_placeholder_is_rejected_when_variables_is_present(tmp_path):
    _write_plugin(
        tmp_path,
        manifest_update={"variables": None},
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                    "note": "${API_TOKEN}",
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("contains placeholder" in err for err in errors), errors
    assert any("${API_TOKEN}" in err for err in errors), errors
    assert any("declares variables" in err for err in errors), errors


def test_invalid_plugin_name_is_rejected(tmp_path):
    _write_plugin(tmp_path, name="Pipefy")
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("name is 'Pipefy'" in err for err in errors), errors


def test_headers_are_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                    "headers": {"Authorization": "Bearer literal-token"},
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("unexpected key 'headers'" in err for err in errors), errors
    # The message reaches public CI logs, so it names the key and never the
    # value: an unenumerated key is where a committed credential would sit.
    assert not any("literal-token" in err for err in errors), errors


def test_unenumerated_server_key_is_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                    "apiKey": "literal-token",
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("unexpected key 'apiKey'" in err for err in errors), errors
    assert not any("literal-token" in err for err in errors), errors


def test_unenumerated_top_level_key_is_rejected(tmp_path):
    # `inputs` with password prompts is a real MCP config shape elsewhere, and
    # it is a credential channel ADR-004 does not pin. The file allows one key.
    _write_plugin(
        tmp_path,
        mcp={
            "inputs": [{"id": "token", "password": True}],
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                }
            },
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("unexpected top-level key 'inputs'" in err for err in errors), errors


def test_unenumerated_auth_key_is_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {
                        "CLIENT_ID": "pipefy-mcp",
                        "client_secret": "literal-secret",
                    },
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("unexpected auth key 'client_secret'" in err for err in errors), errors
    assert not any("literal-secret" in err for err in errors), errors


def test_client_secret_is_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {
                        "CLIENT_ID": "pipefy-mcp",
                        "CLIENT_SECRET": "literal-secret",
                    },
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("unexpected auth key 'CLIENT_SECRET'" in err for err in errors), errors
    assert not any("literal-secret" in err for err in errors), errors


def test_url_must_be_the_hosted_endpoint(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": f"https://evil.example/mcp?token={_SENTINEL}",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    _assert_redacted_field_failure(errors, "url")
    assert any("https://mcp.pipefy.com/mcp" in err for err in errors), errors


def test_client_id_is_required(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {},
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert errors, "expected the lint to fail"
    assert any("auth.CLIENT_ID" in err for err in errors), errors


def test_wrong_client_id_is_rejected_without_echoing_value(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": _SENTINEL},
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    _assert_redacted_field_failure(errors, "auth.CLIENT_ID")
    assert any("pipefy-mcp" in err for err in errors), errors


def test_non_object_auth_is_rejected_without_echoing_value(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": _SENTINEL,
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    _assert_redacted_field_failure(errors, "auth")


def test_non_object_server_is_rejected_without_echoing_value(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={"mcpServers": {"pipefy": _SENTINEL}},
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    _assert_redacted_field_failure(errors, "pipefy")


def test_non_object_mcp_servers_is_rejected_without_echoing_value(tmp_path):
    _write_plugin(tmp_path, mcp={"mcpServers": _SENTINEL})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    _assert_redacted_field_failure(errors, "mcpServers")


def test_zero_mcp_servers_are_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {},
            "note": _SENTINEL,
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    _assert_redacted_field_failure(errors, "0 server")
    assert any("expected exactly one" in err for err in errors), errors


def test_two_mcp_servers_are_rejected(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                },
                "extra": {
                    "url": f"https://evil.example/{_SENTINEL}",
                    "auth": {"CLIENT_ID": _SENTINEL},
                },
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    _assert_redacted_field_failure(errors, "2 server")
    assert any("expected exactly one" in err for err in errors), errors


def test_server_key_must_be_pipefy(tmp_path):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "other": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                }
            }
        },
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("server key is 'other'" in err for err in errors), errors


def test_manifest_mcp_servers_must_point_at_dot_mcp_json(tmp_path):
    _write_plugin(tmp_path, manifest_update={"mcpServers": "./mcp.json"})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("mcpServers is './mcp.json'" in err for err in errors), errors
    assert any("./.mcp.json" in err for err in errors), errors


def test_missing_manifest_mcp_servers_is_rejected(tmp_path):
    _write_plugin(tmp_path, omit=("mcpServers",))
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("mcpServers is None" in err for err in errors), errors
    assert any("./.mcp.json" in err for err in errors), errors


def test_inline_manifest_mcp_servers_are_rejected_without_echoing_value(tmp_path):
    _write_plugin(
        tmp_path,
        manifest_update={"mcpServers": {"pipefy": {"url": _SENTINEL}}},
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("mcpServers is a non-path value" in err for err in errors), errors
    assert _SENTINEL not in "\n".join(errors)


def test_sibling_mcp_json_is_rejected(tmp_path):
    _write_plugin(tmp_path)
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("mcp.json exists" in err for err in errors), errors
    assert any("expected only .mcp.json" in err for err in errors), errors


def test_display_name_must_be_pipefy(tmp_path):
    _write_plugin(tmp_path, manifest_update={"displayName": "Pipefy AI Toolkit"})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("displayName is 'Pipefy AI Toolkit'" in err for err in errors), errors
    assert any("expected 'Pipefy'" in err for err in errors), errors


def test_marketplace_name_must_be_pipefy(tmp_path):
    _write_plugin(tmp_path)
    (tmp_path / ".cursor-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "ai-toolkit", "plugins": []}),
        encoding="utf-8",
    )
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("name is 'ai-toolkit'" in err for err in errors), errors
    assert any("expected 'pipefy'" in err for err in errors), errors


def test_missing_marketplace_is_rejected(tmp_path):
    _write_plugin(tmp_path)
    (tmp_path / ".cursor-plugin" / "marketplace.json").unlink()
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("marketplace.json" in err for err in errors), errors


def test_missing_commands_key_is_rejected(tmp_path):
    _write_plugin(tmp_path, omit=("commands",))
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("commands is None" in err for err in errors), errors


def test_nonempty_commands_are_rejected(tmp_path):
    (tmp_path / "commands").mkdir()
    _write_plugin(tmp_path, manifest_update={"commands": ["./commands"]})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("expected an empty list" in err for err in errors), errors


def test_absolute_logo_is_rejected(tmp_path):
    _write_plugin(tmp_path, manifest_update={"logo": "/etc/hosts"})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("absolute path" in err for err in errors), errors


def test_parent_traversal_logo_is_rejected(tmp_path):
    _write_plugin(tmp_path, manifest_update={"logo": "../outside.png"})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("containing '..'" in err for err in errors), errors


def test_empty_logo_is_rejected(tmp_path):
    _write_plugin(tmp_path, manifest_update={"logo": ""})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("logo is ''" in err for err in errors), errors


def test_logo_directory_is_rejected(tmp_path):
    _write_plugin(tmp_path, manifest_update={"logo": "assets"})
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("is a directory" in err for err in errors), errors


def test_missing_logo_is_rejected(tmp_path):
    _write_plugin(tmp_path, omit=("logo",))
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("logo is missing" in err for err in errors), errors


def test_non_utf8_manifest_is_named(tmp_path):
    _write_plugin(tmp_path)
    (tmp_path / ".cursor-plugin" / "plugin.json").write_bytes(b"\xff\xfe{")
    errors = _lint.collect_errors(tmp_path, [_SKILL_MD])
    assert any("not valid UTF-8" in err for err in errors), errors


def test_main_exits_zero_on_this_repository():
    assert _lint.main() == 0


def test_main_exits_one_when_packaging_errors_exist(monkeypatch, capsys):
    monkeypatch.setattr(_lint, "_tracked_skill_md_paths", lambda root: [_SKILL_MD])
    monkeypatch.setattr(
        _lint, "collect_errors", lambda root, paths: ["packaging error"]
    )
    assert _lint.main() == 1
    captured = capsys.readouterr()
    assert "FAILED" in captured.err
    assert "packaging error" in captured.err


def test_main_stderr_does_not_echo_wrong_client_id(monkeypatch, tmp_path, capsys):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": _SENTINEL},
                }
            }
        },
    )
    monkeypatch.setattr(_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_lint, "_tracked_skill_md_paths", lambda root: [_SKILL_MD])
    assert _lint.main() == 1
    err = capsys.readouterr().err
    assert "FAILED" in err
    assert "auth.CLIENT_ID" in err
    assert _SENTINEL not in err


def test_main_stderr_does_not_echo_wrong_server_count(monkeypatch, tmp_path, capsys):
    _write_plugin(
        tmp_path,
        mcp={
            "mcpServers": {
                "pipefy": {
                    "url": "https://mcp.pipefy.com/mcp",
                    "auth": {"CLIENT_ID": "pipefy-mcp"},
                },
                "extra": {
                    "url": f"https://evil.example/{_SENTINEL}",
                    "auth": {"CLIENT_ID": _SENTINEL},
                },
            }
        },
    )
    monkeypatch.setattr(_lint, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_lint, "_tracked_skill_md_paths", lambda root: [_SKILL_MD])
    assert _lint.main() == 1
    err = capsys.readouterr().err
    assert "FAILED" in err
    assert "2 server" in err
    assert "expected exactly one" in err
    assert _SENTINEL not in err


def test_main_exits_one_when_git_listing_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        _lint,
        "_tracked_skill_md_paths",
        lambda root: "git ls-files failed with exit 1",
    )
    assert _lint.main() == 1
    captured = capsys.readouterr()
    assert "FAILED" in captured.err
    assert "git ls-files failed" in captured.err
