"""Library API tests: typed model, JSON exchange format, coded validation."""

from pathlib import Path

import pytest

from ccpm_scheduler import (
    CcpmError,
    build_schedule,
    check_schedule,
    load_network,
    network_from_json,
    network_to_json,
    validate_network,
    write_build_outputs,
)

DATA = Path(__file__).parent / "data"
GOLDEN = Path(__file__).parent / "golden"

PROJECTS = [
    "example",
    "website-launch",
    "equipment-retrofit",
    "lab-trials",
    "kitchen-renovation",
]


def load(project):
    d = DATA / project
    cal = d / "calendar.csv"
    return load_network(d / "tasks.csv", d / "resources.csv", cal if cal.exists() else None)


def codes(report):
    return {i.code for i in report.issues}


@pytest.mark.parametrize("project", PROJECTS)
def test_api_pipeline_matches_golden(project, tmp_path):
    net = load(project)
    report = validate_network(net)
    assert report.ok, [i.message for i in report.errors]
    result = build_schedule(net, title=project)
    assert check_schedule(result.schedule, net).ok
    write_build_outputs(result, tmp_path)
    for name in ("schedule.csv", "summary.md"):
        assert (tmp_path / name).read_bytes() == (GOLDEN / project / name).read_bytes(), f"{project}/{name}"


@pytest.mark.parametrize("project", PROJECTS)
def test_json_roundtrip_matches_golden(project, tmp_path):
    net = network_from_json(network_to_json(load(project)))
    assert validate_network(net).ok
    result = build_schedule(net, title=project)
    write_build_outputs(result, tmp_path)
    assert (tmp_path / "schedule.csv").read_bytes() == (GOLDEN / project / "schedule.csv").read_bytes()


def test_build_stats():
    result = build_schedule(load("example"), title="example")
    s = result.stats
    assert s.critical_chain == ["A", "B", "D", "F"]
    # default method is cap: PB = Σ safety removed = 30 on this
    # single-point network (docs/buffer-sizing.md)
    assert (s.deadline, s.project_buffer, s.promise_day) == (30, 30, 60)
    assert s.buffer_method == "cap"
    assert s.status_line("example").startswith("example: T=30, CC=A->B->D->F")


def test_build_stats_per_method():
    """The docs' worked numbers for the example network: CC Δs are
    5/10/10/5 (all derived), so cap = 30, hchain = ⌈0.5×30⌉ = 15,
    rsem = ⌈√250⌉ = 16."""
    expected = {"cap": (30, 60), "hchain": (15, 45), "rsem": (16, 46)}
    for method, (pb, promise) in expected.items():
        s = build_schedule(load("example"), title="example", buffer_method=method).stats
        assert (s.project_buffer, s.promise_day) == (pb, promise), method
        assert s.buffer_method == method


def test_unknown_buffer_method_raises():
    with pytest.raises(CcpmError, match="unknown buffer method"):
        build_schedule(load("example"), buffer_method="fancy")


def test_buffer_method_json_key_and_override():
    """The JSON exchange's buffer_method key drives the build; an explicit
    build_schedule argument overrides it; network_to_json round-trips it."""
    data = network_to_json(load("example"))
    data["buffer_method"] = "hchain"
    net = network_from_json(data)
    assert net.buffer_method == "hchain"
    assert network_to_json(net)["buffer_method"] == "hchain"
    assert build_schedule(net).stats.project_buffer == 15  # json key
    assert build_schedule(net, buffer_method="cap").stats.project_buffer == 30  # override


def test_mixed_estimates_buffer_math():
    """Two-point tasks contribute their stated Δ, single-point tasks a
    derived Δ — the mixed 4-task chain from docs/buffer-sizing.md:
    Δ = 4, 10, 5, 10; optimal chain = 31 → cap 29, hchain 16, rsem 16."""

    def net():
        return network_from_json(
            {
                "tasks": [
                    {
                        "id": "A",
                        "realistic_duration": 10,
                        "optimal_duration": 6,
                        "resources": ["r"],
                    },
                    {
                        "id": "B",
                        "realistic_duration": 20,
                        "optimal_duration": 10,
                        "predecessors": "A",
                        "resources": ["r"],
                    },
                    {
                        "id": "C",
                        "realistic_duration": 10,
                        "predecessors": "B",
                        "resources": ["r"],
                    },
                    {
                        "id": "D",
                        "realistic_duration": 20,
                        "predecessors": "C",
                        "resources": ["r"],
                    },
                ],
                "resources": [{"id": "r"}],
            }
        )

    for method, pb in {"cap": 29, "hchain": 16, "rsem": 16}.items():
        stats = build_schedule(net(), buffer_method=method).stats
        assert stats.critical_chain_length == 31
        assert stats.project_buffer == pb, method


def test_optimal_only_task_delta():
    """A task with only an optimal estimate gets realistic = 2 × optimal
    derived, i.e. Δ = optimal (docs/buffer-sizing.md normalization)."""
    net = network_from_json(
        {
            "tasks": [{"id": "A", "optimal_duration": 8, "resources": ["r"]}],
            "resources": [{"id": "r"}],
        }
    )
    assert build_schedule(net, buffer_method="cap").stats.project_buffer == 8
    assert build_schedule(net, buffer_method="rsem").stats.project_buffer == 8


def test_validation_codes_bad_network():
    net = network_from_json(
        {
            "tasks": [
                {
                    "id": "A",
                    "realistic_duration": 4,
                    "predecessors": "B",
                    "resources": ["r1"],
                },
                {
                    "id": "B",
                    "realistic_duration": 4,
                    "predecessors": "A",
                    "resources": ["r1"],
                },
                {"id": "C", "realistic_duration": 4, "resources": []},
                {"id": "D", "realistic_duration": 4.5, "resources": ["r1"]},
                {
                    "id": "E",
                    "realistic_duration": 4,
                    "predecessors": "GHOST",
                    "resources": ["rX"],
                },
            ],
            "resources": [{"id": "r1", "capacity": 1.5}],
        }
    )
    report = validate_network(net)
    assert not report.ok
    assert codes(report) >= {
        "E_CYCLE",
        "E_NO_RESOURCE",
        "E_FRACTIONAL_DURATION",
        "E_UNKNOWN_PRED",
        "E_UNKNOWN_RESOURCE",
        "E_FRACTIONAL_CAPACITY",
    }
    cycle = next(i for i in report.issues if i.code == "E_CYCLE")
    assert set(cycle.task_ids) == {"A", "B"}


def test_fractional_allocation_rejected():
    net = network_from_json(
        {
            "tasks": [{"id": 1, "optimal_duration": 3, "resources": {"7": 0.5}}],
            "resources": [{"id": 7}],
        }
    )
    report = validate_network(net)
    assert "E_FRACTIONAL_ALLOCATION" in codes(report)
    issue = next(i for i in report.issues if i.code == "E_FRACTIONAL_ALLOCATION")
    assert issue.task_ids == ("1",)
    assert issue.resource_ids == ("7",)


def test_our_planner_shape_accepted():
    """Structured predecessors, numeric ids, dict resources with whole
    allocations — the shape our-planner will emit."""
    net = network_from_json(
        {
            "tasks": [
                {
                    "id": 1,
                    "name": "Spec",
                    "realistic_duration": 10,
                    "predecessors": [],
                    "resources": {"1": 1.0},
                },
                {
                    "id": 2,
                    "name": "Build",
                    "realistic_duration": 20,
                    "predecessors": [{"id": 1, "type": "FS", "lag": 0}],
                    "resources": {"2": 1.0},
                },
                {
                    "id": 3,
                    "name": "Overlap",
                    "optimal_duration": 5,
                    "predecessors": [{"id": 2, "type": "SS", "lag": 2}],
                    "resources": {"1": 1},
                },
            ],
            "resources": [{"id": 1, "name": "Dev"}, {"id": 2, "name": "QA"}],
        }
    )
    report = validate_network(net)
    assert report.ok, [i.message for i in report.errors]
    assert [i.code for i in report.warnings] == ["W_NON_FS_LINK"]
    result = build_schedule(net, title="mini")
    assert check_schedule(result.schedule, net).ok
    pb = result.schedule.row("PB")
    assert pb is not None
    assert pb.duration >= 1


def test_check_catches_tampering():
    net = load("example")
    result = build_schedule(net, title="example")
    row = result.schedule.row("B")
    row.start -= 3  # violate precedence with A and overlap resources
    row.finish -= 3
    report = check_schedule(result.schedule, net)
    assert not report.ok
    assert "E_LINK_VIOLATION" in codes(report)


def test_legacy_columns_warn(tmp_path):
    d = DATA / "example"
    legacy = tmp_path / "tasks.csv"
    legacy.write_text((d / "tasks.csv").read_text().replace("predecessor_ids", "predecessors", 1))
    net = load_network(legacy, d / "resources.csv")
    assert [w.code for w in net.io_warnings] == ["W_LEGACY_COLUMNS"]
    assert validate_network(net).ok


def test_unschedulable_raises_named_ccpm_error():
    # Genuinely infeasible: base capacity 0 and no window ever grants any.
    # The error must name the task and the blocking resource (this shape
    # used to hang the forward pass, searching for a window forever).
    net = network_from_json(
        {
            "tasks": [{"id": "A", "name": "Alpha", "optimal_duration": 5, "resources": ["r1"]}],
            "resources": [{"id": "r1", "capacity": 0}],
        }
    )
    with pytest.raises(CcpmError, match=r"task A .*'Alpha'.*r1"):
        build_schedule(net)


def test_finite_outage_schedules_after_it():
    # A finite blackout window is a wait, not infeasibility: the task takes
    # the first feasible execution window after the outage ends. (This
    # exact shape used to raise 'no feasible schedule found' because the
    # deadline search was capped at sum(durations).)
    net = network_from_json(
        {
            "tasks": [{"id": "A", "optimal_duration": 5, "resources": ["r1"]}],
            "resources": [{"id": "r1"}],
            "calendar": [{"resource_id": "r1", "from": 0, "to": 1000, "capacity": 0}],
        }
    )
    result = build_schedule(net)
    row = {r.id: r for r in result.schedule.rows}["A"]
    assert (row.start, row.finish) == (1000, 1005)


def test_calendar_outage_extends_horizon_save1228_shape():
    # Regression for our-planner save-1228.json: 3-task chain, 16 days of
    # work, resource 1 on leave days 5-13. The first task's only feasible
    # window starts at day 13, so the true makespan (29) exceeds the old
    # sum(durations) cap (16) and the build reported 'no feasible
    # schedule'. The horizon must follow the calendar.
    net = network_from_json(
        {
            "tasks": [
                {
                    "id": "5",
                    "name": "ONe",
                    "optimal_duration": 7,
                    "realistic_duration": 12,
                    "resources": ["1"],
                },
                {
                    "id": "6",
                    "name": "two",
                    "optimal_duration": 3,
                    "realistic_duration": 9,
                    "resources": ["2"],
                    "predecessors": [{"id": "5", "type": "FS", "lag": 0}],
                },
                {
                    "id": "7",
                    "name": "three",
                    "optimal_duration": 6,
                    "realistic_duration": 9,
                    "resources": ["3"],
                    "predecessors": [{"id": "6", "type": "FS", "lag": 0}],
                },
            ],
            "resources": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
            "calendar": [{"resource_id": "1", "from": 5, "to": 13, "capacity": 0}],
        }
    )
    result = build_schedule(net)
    rows = {r.id: r for r in result.schedule.rows}
    assert rows["5"].start == 13  # first feasible window is after the leave
    assert rows["7"].finish == 29
    assert result.stats.deadline == 29
    assert check_schedule(result.schedule, net).ok


def test_positive_lag_extends_horizon():
    # Same horizon bug without any calendar: an FS lag pushes the makespan
    # (9) past sum(durations) (4), which used to be the search cap.
    net = network_from_json(
        {
            "tasks": [
                {"id": "A", "optimal_duration": 2, "resources": ["r1"]},
                {
                    "id": "B",
                    "optimal_duration": 2,
                    "resources": ["r2"],
                    "predecessors": [{"id": "A", "type": "FS", "lag": 5}],
                },
            ],
            "resources": [{"id": "r1"}, {"id": "r2"}],
        }
    )
    result = build_schedule(net)
    rows = {r.id: r for r in result.schedule.rows}
    assert rows["B"].start - rows["A"].finish >= 5
    assert result.stats.deadline == 9


def test_report_json_shape():
    report = validate_network(
        network_from_json({"tasks": [{"id": "A", "resources": ["r1"]}], "resources": [{"id": "r1"}]})
    )
    j = report.to_json()
    assert j["ok"] is False
    assert j["issues"][0]["code"] == "E_BAD_DURATION"
    assert j["issues"][0]["task_ids"] == ["A"]


def test_importing_library_does_not_pull_matplotlib():
    import subprocess
    import sys

    code = "import sys; import ccpm_scheduler; sys.exit(1 if 'matplotlib' in sys.modules else 0)"
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_plot_schedule_api(tmp_path):
    from ccpm_scheduler import plot_schedule

    net = load("example")
    result = build_schedule(net, title="example")
    png = tmp_path / "gantt.png"
    plot_schedule(result.schedule, png, resources=net.resources, calendar=net.calendar)
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
