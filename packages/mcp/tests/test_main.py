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
