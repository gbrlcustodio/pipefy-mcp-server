import pytest

from pipefy_mcp import __version__
from pipefy_mcp.main import main


@pytest.mark.unit
def test_entrypoint(mocker):
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main()

    server_mock.assert_called_once()


@pytest.mark.unit
def test_help_skips_server(mocker, capsys):
    """``--help`` prints usage and exits 0 before entering the stdio loop."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])

    assert excinfo.value.code == 0
    server_mock.assert_not_called()
    captured = capsys.readouterr()
    assert "pipefy-mcp-server" in captured.out
    assert "--help" in captured.out
    assert "--version" in captured.out


@pytest.mark.unit
def test_version_skips_server(mocker, capsys):
    """``--version`` prints the installed version, exits 0, and skips the server."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    server_mock.assert_not_called()
    assert capsys.readouterr().out.strip() == __version__


@pytest.mark.unit
def test_unknown_flag_still_starts_server(mocker):
    """Anything not ``--help`` / ``--version`` is delegated to ``run_server``.

    The MCP transport ignores extra argv, so we keep the binary forgiving rather
    than failing on flags that downstream tooling may inject (e.g. IDE wrappers).
    """
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--unknown-flag"])

    server_mock.assert_called_once()


@pytest.mark.unit
def test_profile_remote_passes_through(mocker):
    """``--profile remote`` is resolved and the Settings handed to ``run_server``."""
    resolve_mock = mocker.patch("pipefy_mcp.main.resolve_mcp_settings")
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "remote"])

    # Only the flags actually passed reach resolve_mcp_settings; the rest stay
    # None so it applies the profile-derived transport and PIPEFY_MCP_* defaults.
    resolve_mock.assert_called_once_with(
        profile="remote", transport=None, host=None, port=None, toolsets=None
    )
    server_mock.assert_called_once_with(resolve_mock.return_value)


@pytest.mark.unit
def test_explicit_transport_passes_through(mocker):
    """``--transport`` is resolved alongside the profile (e.g. local over http)."""
    resolve_mock = mocker.patch("pipefy_mcp.main.resolve_mcp_settings")
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "local", "--transport", "http"])

    resolve_mock.assert_called_once_with(
        profile="local", transport="http", host=None, port=None, toolsets=None
    )
    server_mock.assert_called_once_with(resolve_mock.return_value)


@pytest.mark.unit
def test_host_and_port_overrides(mocker):
    """``--host`` / ``--port`` reach resolve_mcp_settings as overrides."""
    resolve_mock = mocker.patch("pipefy_mcp.main.resolve_mcp_settings")
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "remote", "--host", "0.0.0.0", "--port", "9001"])

    resolve_mock.assert_called_once_with(
        profile="remote", transport=None, host="0.0.0.0", port=9001, toolsets=None
    )
    server_mock.assert_called_once_with(resolve_mock.return_value)


@pytest.mark.unit
def test_host_and_port_equals_form(mocker):
    """``--host=`` / ``--port=`` forms are accepted too."""
    resolve_mock = mocker.patch("pipefy_mcp.main.resolve_mcp_settings")
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "remote", "--host=127.0.0.2", "--port=9002"])

    resolve_mock.assert_called_once_with(
        profile="remote", transport=None, host="127.0.0.2", port=9002, toolsets=None
    )
    server_mock.assert_called_once_with(resolve_mock.return_value)


@pytest.mark.unit
def test_toolsets_passes_through(mocker):
    """``--toolsets`` reaches resolve_mcp_settings as an override."""
    resolve_mock = mocker.patch("pipefy_mcp.main.resolve_mcp_settings")
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--toolsets", "workflow,database"])

    resolve_mock.assert_called_once_with(
        profile=None,
        transport=None,
        host=None,
        port=None,
        toolsets="workflow,database",
    )
    server_mock.assert_called_once_with(resolve_mock.return_value)


@pytest.mark.unit
def test_tools_is_an_alias_for_toolsets(mocker):
    """``--tools`` sets the same value as ``--toolsets``."""
    resolve_mock = mocker.patch("pipefy_mcp.main.resolve_mcp_settings")
    mocker.patch("pipefy_mcp.main.run_server")

    main(["--tools", "workflow"])

    assert resolve_mock.call_args.kwargs["toolsets"] == "workflow"


@pytest.mark.unit
def test_unknown_toolset_is_a_usage_error(mocker, capsys):
    """An unknown ``--toolsets`` name exits 2 and never builds the server."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main(["--toolsets", "bogus"])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()
    assert "unknown toolset" in capsys.readouterr().err.lower()


@pytest.mark.unit
def test_unknown_toolset_from_env_is_a_usage_error(monkeypatch, mocker, capsys):
    """An unknown ``PIPEFY_MCP_TOOLSETS`` (no flag) gets the same exit-2 usage error.

    The resolved value (flag merged with env) is validated in ``main``, so an
    env-only bad name fails the same way as ``--toolsets`` rather than as a build
    traceback.
    """
    monkeypatch.setenv("PIPEFY_MCP_TOOLSETS", "bogus")
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main([])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()
    assert "unknown toolset" in capsys.readouterr().err.lower()


@pytest.mark.unit
@pytest.mark.parametrize("bad_port", ["abc", ""])
def test_rejects_a_non_integer_port(mocker, bad_port):
    """A non-integer ``--port`` exits with a usage error instead of crashing."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main(["--profile", "remote", "--port", bad_port])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "flag,value", [("--profile", "bogus"), ("--transport", "carrier-pigeon")]
)
def test_rejects_unknown_choice(mocker, flag, value):
    """An unknown ``--profile`` / ``--transport`` value exits 2, not a traceback."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main([flag, value])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()


@pytest.mark.unit
def test_rejects_remote_over_stdio(mocker):
    """``--profile remote --transport stdio`` exits 2 without starting the server.

    The rule lives once, in the McpSettings validator; main resolves the flags
    and surfaces the resulting ValueError as a usage error before run_server.
    """
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main(["--profile", "remote", "--transport", "stdio"])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("bad_host", ["", "   ", "--host="])
def test_rejects_an_empty_host(mocker, bad_host):
    """An empty ``--host`` exits 2 instead of overriding the default with ''.

    Without the guard, an empty value reaches ``resolve_mcp_settings`` as an
    explicit init-kwarg, silently displacing the ``127.0.0.1`` default and later
    tripping the bind-safety interlock with a misleading non-loopback error.
    """
    server_mock = mocker.patch("pipefy_mcp.main.run_server")
    argv = [bad_host] if bad_host.startswith("--host=") else ["--host", bad_host]

    with pytest.raises(SystemExit) as excinfo:
        main([*argv, "--transport", "http"])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()
