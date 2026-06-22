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
    """``--help`` must short-circuit before entering the stdio loop."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--help"])

    server_mock.assert_not_called()
    captured = capsys.readouterr()
    assert "pipefy-mcp-server" in captured.out
    assert "--help" in captured.out
    assert "--version" in captured.out


@pytest.mark.unit
def test_version_skips_server(mocker, capsys):
    """``--version`` must print the installed version and skip the server."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--version"])

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
def test_remote_starts_http_server_with_remote_profile(mocker):
    """``--remote`` drives the unified server over HTTP with the remote profile."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--remote"])

    server_mock.assert_called_once()
    _, kwargs = server_mock.call_args
    assert kwargs["http"] is True
    assert kwargs["remote_mode"] is True
    # Unset flags pass through as None; run_server resolves the settings defaults.
    assert kwargs["host"] is None
    assert kwargs["port"] is None


@pytest.mark.unit
def test_remote_host_and_port_overrides(mocker):
    """``--host`` / ``--port`` override the settings defaults under ``--remote``."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--remote", "--host", "0.0.0.0", "--port", "9001"])

    _, kwargs = server_mock.call_args
    assert kwargs["http"] is True
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9001
    assert kwargs["remote_mode"] is True


@pytest.mark.unit
def test_remote_host_and_port_equals_form(mocker):
    """``--host=`` / ``--port=`` forms are accepted too."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--remote", "--host=127.0.0.2", "--port=9002"])

    _, kwargs = server_mock.call_args
    assert kwargs["http"] is True
    assert kwargs["host"] == "127.0.0.2"
    assert kwargs["port"] == 9002


@pytest.mark.unit
@pytest.mark.parametrize("bad_port", ["abc", ""])
def test_remote_rejects_a_non_integer_port(mocker, bad_port):
    """A non-integer ``--port`` exits with a usage error instead of crashing."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    with pytest.raises(SystemExit) as excinfo:
        main(["--remote", "--port", bad_port])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()
