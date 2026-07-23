"""Tests for the interactive network-graph HTML (graph subcommand)."""

import json
import re
import subprocess
import sys
from pathlib import Path

from ccpm_scheduler import build_schedule, load_network, render_network_html

DATA = Path(__file__).parent / "data"


def example_schedule():
    d = DATA / "example"
    net = load_network(d / "tasks.csv", d / "resources.csv", d / "calendar.csv")
    return build_schedule(net, title="example").schedule


def embedded_graph(html):
    m = re.search(r"const GRAPH = (\{.*?\});\n", html, re.S)
    assert m, "embedded GRAPH payload not found"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_html_structure_and_payload():
    schedule = example_schedule()
    html = render_network_html(schedule, title="My <plan> & co")
    assert html.startswith("<!DOCTYPE html>")
    assert "unpkg.com/vis-network" in html
    assert "My &lt;plan&gt; &amp; co" in html  # title escaped

    graph = embedded_graph(html)
    assert {n["id"] for n in graph["nodes"]} == {r.id for r in schedule.rows}
    # every parsed predecessor link becomes an edge
    assert len(graph["edges"]) == sum(
        len([t for t in r.predecessor_ids.replace(";", " ").split() if t]) for r in schedule.rows
    )
    # buffer attachments render dashed, plain FS edges solid and unlabeled
    fb_edge = next(e for e in graph["edges"] if e["to"] == "FB1")
    assert fb_edge["dashes"]
    assert "label" not in fb_edge
    fs_edge = next(e for e in graph["edges"] if e["to"] == "B" and e["from"] == "A")
    assert fs_edge["dashes"] is False
    assert "label" not in fs_edge
    # critical chain / buffers colored per the Gantt code
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["A"]["color"]["background"] == "#b22222"
    assert by_id["PB"]["color"]["background"] == "#ffd700"
    assert by_id["PB"]["shapeProperties"]["borderDashes"] == [4, 3]
    # inspector payload carries the row data
    assert by_id["B"]["data"]["duration"] == 10
    assert by_id["B"]["data"]["resources"] == "green"
    # legend and summary present
    assert {item["label"] for item in graph["legend"]} >= {
        "Critical chain",
        "Project buffer",
        "Feeding buffer",
    }
    assert "promised completion: day 60" in graph["summary"]


def test_script_injection_guarded():
    schedule = example_schedule()
    schedule.rows[0].name = "sneaky</script><script>alert(1)"
    html = render_network_html(schedule)
    # the raw terminator must not appear inside the embedded payload
    payload = html.split("const GRAPH = ", 1)[1]
    assert "</script><script>" not in payload.split("</script>")[0]


def test_zero_duration_milestone_is_diamond():
    d = DATA / "lab-trials"  # produces a FINISH milestone
    net = load_network(d / "tasks.csv", d / "resources.csv")
    schedule = build_schedule(net, title="lab").schedule
    graph = embedded_graph(render_network_html(schedule))
    finish = next(n for n in graph["nodes"] if n["id"] == "FINISH")
    assert finish["shape"] == "diamond"


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "ccpm_scheduler", *map(str, args)],
        capture_output=True,
        text=True,
    )


def test_cli_graph(tmp_path):
    d = DATA / "example"
    cli(
        "build",
        d / "tasks.csv",
        d / "resources.csv",
        "--calendar",
        d / "calendar.csv",
        "--out-dir",
        tmp_path,
        "--title",
        "example",
    )
    out = tmp_path / "project-network.html"
    r = cli("graph", tmp_path / "schedule.csv", out, "--title", "example", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ok"] is True
    html = out.read_text()
    assert "vis-network" in html
    assert '"id": "PB"' in html

    # deterministic: a second render is byte-identical
    out2 = tmp_path / "again.html"
    cli("graph", tmp_path / "schedule.csv", out2, "--title", "example")
    assert out.read_bytes() == out2.read_bytes()


def test_cli_graph_missing_schedule_exit_2(tmp_path):
    r = cli("graph", tmp_path / "nope.csv", tmp_path / "out.html")
    assert r.returncode == 2


def test_realistic_estimates_from_schedule():
    """Since v0.7 schedule.csv carries realistic_duration - no --tasks needed."""
    html = render_network_html(example_schedule())
    graph = embedded_graph(html)
    by_id = {n["id"]: n for n in graph["nodes"]}
    # example: A realistic 10 -> scheduled (optimal) 5
    assert by_id["A"]["data"]["realistic"] == 10
    assert by_id["A"]["data"]["duration"] == 5
    assert "5d optimal, 10d realistic" in by_id["A"]["title"]
    # buffers carry no estimate
    assert by_id["PB"]["data"]["realistic"] is None
    assert "realistic" not in by_id["PB"]["title"]


def test_tasks_fallback_for_pre_v07_schedules():
    """Older schedule.csv files lack the column - --tasks still fills it."""
    from ccpm_scheduler import load_tasks

    d = DATA / "example"
    schedule = example_schedule()
    for r in schedule.rows:
        r.realistic_duration = None  # simulate a pre-v0.7 schedule
    assert embedded_graph(render_network_html(schedule))["nodes"][0]["data"]["realistic"] is None
    graph = embedded_graph(render_network_html(schedule, tasks=load_tasks(d / "tasks.csv")))
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["A"]["data"]["realistic"] == 10


def test_resource_filter_payload():
    graph = embedded_graph(render_network_html(example_schedule()))
    assert graph["resources"] == ["blue", "green", "red"]
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["B"]["data"]["resource_list"] == ["green"]
    assert by_id["PB"]["data"]["resource_list"] == []
    # edges carry ids so the filter can fade them
    assert all(e["id"].startswith("e") for e in graph["edges"])
    html = render_network_html(example_schedule())
    assert 'id="resource-filter"' in html
    assert "__unassigned__" in html


def test_cli_graph_with_tasks(tmp_path):
    d = DATA / "example"
    cli(
        "build",
        d / "tasks.csv",
        d / "resources.csv",
        "--calendar",
        d / "calendar.csv",
        "--out-dir",
        tmp_path,
        "--title",
        "example",
    )
    out = tmp_path / "project-network.html"
    r = cli(
        "graph",
        tmp_path / "schedule.csv",
        out,
        "--tasks",
        d / "tasks.csv",
        "--title",
        "example",
    )
    assert r.returncode == 0, r.stderr
    assert '"realistic": 10' in out.read_text()


def test_resource_names_with_spaces():
    """Resource lists split on ';' only — names may contain spaces (as when
    an embedding tool passes human-readable resource names)."""
    from ccpm_scheduler import Schedule, ScheduleRow

    schedule = Schedule(
        rows=[
            ScheduleRow(
                id="T1",
                name="Task one",
                type="task",
                chain="none",
                start=0,
                finish=2,
                duration=2,
                resource_ids="Resource A;Resource B",
            ),
            ScheduleRow(
                id="T2",
                name="Task two",
                type="task",
                chain="none",
                start=2,
                finish=4,
                duration=2,
                resource_ids="Resource A",
                predecessor_ids="T1",
            ),
        ]
    )
    graph = embedded_graph(render_network_html(schedule))
    assert graph["resources"] == ["Resource A", "Resource B"]
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["T1"]["data"]["resource_list"] == ["Resource A", "Resource B"]
    assert by_id["T1"]["data"]["resources"] == "Resource A, Resource B"


def test_custom_chain_labels():
    """Any chain label (not just feeding-<n>) gets a palette color and its
    verbatim name in the legend; feeding-<n> keeps the friendly label."""
    from ccpm_scheduler import Schedule, ScheduleRow

    def row(rid, chain, **kw):
        return ScheduleRow(
            id=rid,
            name=rid,
            type="task",
            chain=chain,
            start=0,
            finish=1,
            duration=1,
            **kw,
        )

    schedule = Schedule(
        rows=[
            row("A", "critical"),
            row("B", "Integration stream"),
            row("C", "feeding-2"),
            row("D", "none"),
        ]
    )
    graph = embedded_graph(render_network_html(schedule))
    by_id = {n["id"]: n for n in graph["nodes"]}
    grey = by_id["D"]["color"]["background"]
    assert by_id["B"]["color"]["background"] != grey  # palette, not grey
    assert by_id["B"]["color"]["background"] != by_id["C"]["color"]["background"]  # distinct colors
    labels = {item["label"] for item in graph["legend"]}
    assert "Integration stream" in labels
    assert "Feeding chain 2" in labels
