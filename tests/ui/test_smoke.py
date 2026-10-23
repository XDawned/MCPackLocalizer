# [Module: tests.smoke] [Status: 已完成] [Brief: 发布冒烟检查必须显示窗口并等待扫描与 GC 观察都完成]
import heapq
import json

import pytest

from mcpacklocalizer.ui import smoke


@pytest.mark.parametrize("scan_delay,quit_early", [(10, False), (4500, False), (None, False), (10, True)])
def test_smoke_waits_for_visible_gc_observation_and_scan(tmp_path, mocker, scan_delay, quit_early):
    output = tmp_path / "smoke.json"
    mocker.patch.object(smoke.sys, "argv", ["desktop", "--release-smoke-test", str(output), str(tmp_path)])
    temporary = mocker.patch.object(smoke.tempfile, "TemporaryDirectory")
    temporary.return_value.__enter__.return_value = str(tmp_path)
    mocker.patch.object(smoke, "QSettings")
    app = mocker.Mock()
    mocker.patch.object(smoke, "QApplication", return_value=app)
    window = mocker.Mock()
    window.runner.busy = False
    mocker.patch.object(smoke, "MainWindow", return_value=window)
    collector = mocker.patch.object(smoke.gc, "collect")
    clock = 0
    events = []
    sequence = 0
    stopped = False
    done = []
    shown = []
    collections = []
    window.runner.done.connect.side_effect = done.append
    window.show.side_effect = lambda: shown.append(clock)
    collector.side_effect = lambda: collections.append(clock)

    def schedule(delay, callback):
        nonlocal sequence
        sequence += 1
        heapq.heappush(events, (clock + delay, sequence, callback))

    def timer_factory(parent):
        timer = mocker.Mock()
        callbacks = []
        timer.timeout.connect.side_effect = callbacks.append
        timer.start.side_effect = lambda delay: schedule(delay, lambda: [callback() for callback in callbacks])
        return timer

    timer = mocker.patch.object(smoke, "QTimer", side_effect=timer_factory)
    timer.singleShot.side_effect = schedule

    def start(job):
        assert job.operation == "scan" and job.recognition_scope == "kubejs"
        if scan_delay is not None:
            schedule(scan_delay, lambda: done[0](0, {"entries": 1}, False))

    def quit_app():
        nonlocal stopped
        stopped = True

    def execute():
        nonlocal clock
        if quit_early:
            schedule(20, quit_app)
        while not stopped:
            clock, _, callback = heapq.heappop(events)
            callback()

    app.quit.side_effect = quit_app
    app.exec.side_effect = execute
    window.runner.start.side_effect = start
    code = smoke.main()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert shown == [0]
    assert collections == ([0] if quit_early else [0, 100])
    assert report["ui"] == {"observation_complete": not quit_early, "gc_cycles": len(collections)}
    if quit_early:
        assert code == report["code"] == 2 and "观察未完成" in report["result"]["error"]
    elif scan_delay is None:
        assert clock == 90000 and code == report["code"] == 2
        assert "超时" in report["result"]["error"]
    else:
        assert clock == max(smoke.OBSERVATION_MS, scan_delay)
        assert code == report["code"] == 0 and report["result"]["entries"] == 1
    window.deleteLater.assert_called_once()
    app.sendPostedEvents.assert_called_once()
