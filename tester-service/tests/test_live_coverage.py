"""Real collector context/snapshot isolation without network or a database."""

import importlib.util
import json


def test_active_collector_snapshot_excludes_startup_and_other_run_branches(tmp_path):
    import coverage
    from autograder.live_coverage import snapshot_report

    source = tmp_path / "sample.py"
    source.write_text("def choose(flag):\n    if flag:\n        return 11\n    return 22\n")
    collector = coverage.Coverage(
        data_file=None, branch=True, config_file=False, include=[str(source)]
    )
    collector.start()
    try:
        spec = importlib.util.spec_from_file_location("sample", source)
        sample = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sample)
        collector.switch_context("other|cra-service/test_api.py::test_other")
        assert sample.choose(False) == 22
        collector.switch_context("current|cra-service/test_api.py::test_current")
        assert sample.choose(True) == 11
        collector.switch_context("unattributed")
        path = tmp_path / "snapshot.json"
        snapshot_report(collector, [source], path, "current")
        result = next(iter(json.loads(path.read_text())["files"].values()))
        assert set(result["executed_lines"]) == {2, 3}
        assert [2, 4] not in result["executed_branches"]
        assert result["executed_branches"] == [[2, 3]]
        # Original collector remains active for later sessions/worker threads.
        collector.switch_context("later|cra-service/test_api.py::test_later")
        assert sample.choose(False) == 22
        snapshot_report(collector, [source], path, "later")
        later = next(iter(json.loads(path.read_text())["files"].values()))
        assert set(later["executed_lines"]) == {2, 4}
    finally:
        collector.stop()


def test_multiline_condition_contexts_bind_to_real_logical_statement(tmp_path):
    import coverage
    from autograder.live_coverage import snapshot_report

    source = tmp_path / "multiline.py"
    source.write_text(
        "def choose(a, b):\n    if (\n        a\n        and b\n    ):\n        return 11\n    return 22\n"
    )
    collector = coverage.Coverage(
        data_file=None, branch=True, config_file=False, include=[str(source)]
    )
    collector.start()
    try:
        spec = importlib.util.spec_from_file_location("multiline", source)
        sample = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sample)
        context = "current|cra-service/test_api.py::test_current"
        collector.switch_context(context)
        assert sample.choose(True, True) == 11
        collector.switch_context("unattributed")
        path = tmp_path / "trace.json"
        snapshot_report(collector, [source], path, "current")
        data = next(iter(json.loads(path.read_text())["files"].values()))
        assert 2 in data["executed_lines"] and 7 in data["missing_lines"]
        assert [2, 6] in data["executed_branches"] and [2, 7] not in data["executed_branches"]
    finally:
        collector.stop()
