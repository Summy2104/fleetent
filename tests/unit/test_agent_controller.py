"""Start/stop controller: spawn `fleetent agent run <name>`, track PID, no monitoring."""

from fleetent.platform.agent_lifecycle import controller


class _FakeProc:
    def __init__(self, pid=4242):
        self.pid = pid
        self._rc = None  # None = still running
        self.terminated = False

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = -15

    def exit(self, code=0):
        self._rc = code


def test_build_command_targets_agent_run():
    cmd = controller._build_command("support")
    # spawns the `fleetent agent run support` runtime
    assert cmd[-3:] == ["agent", "run", "support"]


def test_start_spawns_and_records_pid():
    spawned = []

    def fake_spawn(name):
        spawned.append(name)
        return _FakeProc(pid=999)

    ctrl = controller.AgentController(spawn=fake_spawn)
    pid = ctrl.start("support")
    assert spawned == ["support"]
    assert pid == 999
    assert ctrl.is_running("support") is True


def test_stop_terminates_tracked_process():
    proc = _FakeProc()

    ctrl = controller.AgentController(spawn=lambda name: proc)
    ctrl.start("support")
    assert ctrl.stop("support") is True
    assert proc.terminated is True
    assert ctrl.is_running("support") is False


def test_stop_unknown_agent_is_false():
    ctrl = controller.AgentController(spawn=lambda name: _FakeProc())
    assert ctrl.stop("never-started") is False


def test_exited_process_reported_not_running_and_not_restarted():
    proc = _FakeProc()
    spawn_count = {"n": 0}

    def fake_spawn(name):
        spawn_count["n"] += 1
        return proc

    ctrl = controller.AgentController(spawn=fake_spawn)
    ctrl.start("support")
    proc.exit(0)  # the process dies on its own
    assert ctrl.is_running("support") is False
    # no supervision: checking status must not re-spawn
    assert spawn_count["n"] == 1
