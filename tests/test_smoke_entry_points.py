"""Tests for scripts/smoke_entry_points.py.

The script itself only runs inside a throwaway virtualenv in CI, so the logic that
decides *what* to launch -- and what counts as a failure -- is covered here, where
it runs on every suite. The two drift tests at the bottom are the point of the
explicit constants: they tie them to the workspace's own `pyproject.toml` files,
so adding a package or an entry point fails the suite instead of quietly
narrowing what the packaging gate checks.
"""

from __future__ import annotations

import importlib.util
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "smoke_entry_points.py"
_spec = importlib.util.spec_from_file_location("smoke_entry_points", _SCRIPT)
assert _spec and _spec.loader
_smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_smoke)


@dataclass(frozen=True)
class FakeEntryPoint:
    name: str
    group: str = "console_scripts"


@dataclass(frozen=True)
class FakeDistribution:
    """Stands in for importlib.metadata.Distribution: name plus entry points."""

    name: str
    entry_points: tuple[FakeEntryPoint, ...] = ()


def _full_install() -> list[FakeDistribution]:
    """Every published member installed, with the scripts they really ship."""
    return [
        FakeDistribution("pipefy"),
        FakeDistribution("pipefy-auth"),
        FakeDistribution("pipefy-infra"),
        FakeDistribution("pipefy-cli", (FakeEntryPoint("pipefy"),)),
        FakeDistribution("pipefy-mcp-server", (FakeEntryPoint("pipefy-mcp-server"),)),
    ]


@dataclass
class FakeRunner:
    """Records the argv of each launch and replays canned results."""

    returncode: int = 0
    stderr: str = ""
    stdout: str = ""
    raises: BaseException | None = None
    calls: list[list[str]] = field(default_factory=list)

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(
            argv, self.returncode, stdout=self.stdout, stderr=self.stderr
        )


class TestCanonicalName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("pipefy-cli", "pipefy-cli"),
            ("pipefy_cli", "pipefy-cli"),
            ("Pipefy_MCP.Server", "pipefy-mcp-server"),
            ("pipefy__cli", "pipefy-cli"),
        ],
    )
    def test_normalizes_to_pep_503(self, raw: str, expected: str) -> None:
        assert _smoke.canonical_name(raw) == expected


class TestIndexPublished:
    def test_keeps_only_workspace_members(self) -> None:
        dists = [*_full_install(), FakeDistribution("httpx"), FakeDistribution("typer")]
        assert set(_smoke.index_published(dists)) == set(_smoke.PUBLISHED_DISTRIBUTIONS)

    def test_indexes_wheel_style_names_under_their_canonical_form(self) -> None:
        """A wheel records `pipefy_mcp_server`; the constant spells it with hyphens."""
        found = _smoke.index_published([FakeDistribution("pipefy_mcp_server")])
        assert set(found) == {"pipefy-mcp-server"}


class TestResolveScripts:
    def test_names_the_member_missing_from_the_install(self) -> None:
        partial = [d for d in _full_install() if d.name != "pipefy-infra"]
        with pytest.raises(
            _smoke.SmokeError, match="missing from the install: pipefy-infra"
        ):
            _smoke.resolve_scripts(_smoke.index_published(partial))

    def test_fails_when_an_installed_wheel_ships_no_entry_point(self) -> None:
        """Discovery alone would read a lost script as success; the floor catches it."""
        without_mcp_script = [
            d
            if d.name != "pipefy-mcp-server"
            else FakeDistribution("pipefy-mcp-server")
            for d in _full_install()
        ]
        with pytest.raises(
            _smoke.SmokeError, match="no console script named pipefy-mcp-server"
        ):
            _smoke.resolve_scripts(_smoke.index_published(without_mcp_script))

    def test_returns_the_required_scripts_sorted(self) -> None:
        scripts = _smoke.resolve_scripts(_smoke.index_published(_full_install()))
        assert scripts == ["pipefy", "pipefy-mcp-server"]

    def test_covers_a_newly_added_entry_point_without_a_code_change(self) -> None:
        extended = [
            d
            if d.name != "pipefy-cli"
            else FakeDistribution(
                "pipefy-cli", (FakeEntryPoint("pipefy"), FakeEntryPoint("pipefy-admin"))
            )
            for d in _full_install()
        ]
        scripts = _smoke.resolve_scripts(_smoke.index_published(extended))
        assert scripts == ["pipefy", "pipefy-admin", "pipefy-mcp-server"]

    def test_ignores_non_console_entry_points(self) -> None:
        with_plugin = [
            d
            if d.name != "pipefy"
            else FakeDistribution(
                "pipefy", (FakeEntryPoint("some_plugin", group="pytest11"),)
            )
            for d in _full_install()
        ]
        scripts = _smoke.resolve_scripts(_smoke.index_published(with_plugin))
        assert scripts == ["pipefy", "pipefy-mcp-server"]


class TestLaunch:
    def test_runs_help_for_each_script_from_the_venv_bin(self, tmp_path: Path) -> None:
        for name in ("pipefy", "pipefy-mcp-server"):
            (tmp_path / name).touch()
        runner = FakeRunner()
        _smoke.launch(["pipefy", "pipefy-mcp-server"], tmp_path, runner=runner)
        assert runner.calls == [
            [str(tmp_path / "pipefy"), "--help"],
            [str(tmp_path / "pipefy-mcp-server"), "--help"],
        ]

    def test_fails_when_the_declared_script_is_not_on_disk(
        self, tmp_path: Path
    ) -> None:
        runner = FakeRunner()
        with pytest.raises(_smoke.SmokeError, match="does not exist"):
            _smoke.launch(["pipefy"], tmp_path, runner=runner)
        assert runner.calls == []

    def test_surfaces_the_exit_code_and_stderr(self, tmp_path: Path) -> None:
        (tmp_path / "pipefy").touch()
        runner = FakeRunner(
            returncode=1, stderr="ModuleNotFoundError: mcp.server.fastmcp"
        )
        with pytest.raises(_smoke.SmokeError, match="mcp.server.fastmcp") as excinfo:
            _smoke.launch(["pipefy"], tmp_path, runner=runner)
        assert "exited 1" in str(excinfo.value)

    def test_falls_back_to_stdout_when_stderr_is_empty(self, tmp_path: Path) -> None:
        (tmp_path / "pipefy").touch()
        runner = FakeRunner(returncode=2, stdout="usage error on stdout")
        with pytest.raises(_smoke.SmokeError, match="usage error on stdout"):
            _smoke.launch(["pipefy"], tmp_path, runner=runner)

    def test_a_hung_launch_is_a_failure_not_a_stall(self, tmp_path: Path) -> None:
        (tmp_path / "pipefy").touch()
        runner = FakeRunner(raises=subprocess.TimeoutExpired(cmd="pipefy", timeout=120))
        with pytest.raises(_smoke.SmokeError, match="did not return within"):
            _smoke.launch(["pipefy"], tmp_path, runner=runner)

    def test_stops_at_the_first_failure(self, tmp_path: Path) -> None:
        for name in ("pipefy", "pipefy-mcp-server"):
            (tmp_path / name).touch()
        runner = FakeRunner(returncode=1)
        with pytest.raises(_smoke.SmokeError):
            _smoke.launch(["pipefy", "pipefy-mcp-server"], tmp_path, runner=runner)
        assert len(runner.calls) == 1


class TestMain:
    def test_reports_failure_on_stderr_and_exits_non_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(_smoke, "distributions", lambda: [])
        assert _smoke.main() == 1
        assert "packaging smoke failed" in capsys.readouterr().err

    def test_succeeds_when_every_entry_point_launches(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        for name in ("pipefy", "pipefy-mcp-server"):
            (tmp_path / name).touch()
        monkeypatch.setattr(_smoke, "distributions", _full_install)
        monkeypatch.setattr(_smoke.sysconfig, "get_path", lambda _name: str(tmp_path))
        monkeypatch.setattr(_smoke.subprocess, "run", FakeRunner())
        assert _smoke.main() == 0
        assert (
            "Every published console entry point launched." in capsys.readouterr().out
        )


class TestConstantsTrackTheWorkspace:
    """The explicit constants exist to force a decision when packaging changes."""

    @staticmethod
    def _workspace_pyprojects() -> list[dict]:
        return [
            tomllib.loads(path.read_text(encoding="utf-8"))
            for path in sorted((_REPO_ROOT / "packages").glob("*/pyproject.toml"))
        ]

    def test_published_distributions_matches_the_workspace_members(self) -> None:
        declared = {
            _smoke.canonical_name(data["project"]["name"])
            for data in self._workspace_pyprojects()
        }
        assert declared == set(_smoke.PUBLISHED_DISTRIBUTIONS)

    def test_required_scripts_matches_the_declared_console_scripts(self) -> None:
        declared = {
            name
            for data in self._workspace_pyprojects()
            for name in data["project"].get("scripts", {})
        }
        assert declared == set(_smoke.REQUIRED_SCRIPTS)
