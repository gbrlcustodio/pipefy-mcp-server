import pytest

from pipefy_mcp.main import main


@pytest.mark.unit
def test_entrypoint(mocker):
    server_mock = mocker.patch("pipefy_mcp.main.run_server")

    main()

    server_mock.assert_called_once()
