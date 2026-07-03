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
    """``--profile remote`` reaches ``run_server``; transport stays unset for it to resolve."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "remote"])

    server_mock.assert_called_once()
    _, kwargs = server_mock.call_args
    assert kwargs["profile"] == "remote"
    # Unset flags pass through as None; run_server resolves the profile-derived
    # transport default and the PIPEFY_MCP_* host/port.
    assert kwargs["transport"] is None
    assert kwargs["host"] is None
    assert kwargs["port"] is None


@pytest.mark.unit
def test_explicit_transport_passes_through(mocker):
    """``--transport`` reaches ``run_server`` alongside the profile (e.g. local over http)."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "local", "--transport", "http"])

    _, kwargs = server_mock.call_args
    assert kwargs["profile"] == "local"
    assert kwargs["transport"] == "http"


@pytest.mark.unit
def test_host_and_port_overrides(mocker):
    """``--host`` / ``--port`` override the settings defaults."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "remote", "--host", "0.0.0.0", "--port", "9001"])

    _, kwargs = server_mock.call_args
    assert kwargs["profile"] == "remote"
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9001


@pytest.mark.unit
def test_host_and_port_equals_form(mocker):
    """``--host=`` / ``--port=`` forms are accepted too."""
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main(["--profile", "remote", "--host=127.0.0.2", "--port=9002"])

    _, kwargs = server_mock.call_args
    assert kwargs["host"] == "127.0.0.2"
    assert kwargs["port"] == 9002


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
    """``--profile remote --transport stdio`` is refused at the argv boundary."""
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
    failing the loopback check with a misleading non-loopback error.
    """
    server_mock = mocker.patch("pipefy_mcp.main.run_server")
    argv = [bad_host] if bad_host.startswith("--host=") else ["--host", bad_host]

    with pytest.raises(SystemExit) as excinfo:
        main([*argv, "--transport", "http"])

    assert excinfo.value.code == 2
    server_mock.assert_not_called()
