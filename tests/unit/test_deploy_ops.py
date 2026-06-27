from __future__ import annotations

from fleetent import deploy_ops


def test_deployment_status_reports_stale_with_both_commits() -> None:
    status = deploy_ops.compare_commits(deployed_commit="abc1234", head_commit="def5678")

    assert status.is_stale is True
    assert status.deployed_commit == "abc1234"
    assert status.head_commit == "def5678"
    assert "stale" in status.message
    assert "abc1234" in status.message
    assert "def5678" in status.message


def test_deployment_status_reports_current_when_commits_match() -> None:
    status = deploy_ops.compare_commits(deployed_commit="abc1234", head_commit="abc1234")

    assert status.is_stale is False
    assert status.message == "deployment current: abc1234"


def test_redeploy_does_not_restart_when_build_fails() -> None:
    calls: list[str] = []

    def build() -> int:
        calls.append("build")
        return 12

    def restart() -> int:
        calls.append("restart")
        return 0

    result = deploy_ops.redeploy(build=build, restart=restart)

    assert result == 12
    assert calls == ["build"]


def test_redeploy_restarts_after_successful_build() -> None:
    calls: list[str] = []

    def build() -> int:
        calls.append("build")
        return 0

    def restart() -> int:
        calls.append("restart")
        return 0

    result = deploy_ops.redeploy(build=build, restart=restart)

    assert result == 0
    assert calls == ["build", "restart"]
