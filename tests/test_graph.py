"""Tests for the interactive network-graph HTML (graph subcommand)."""

import json
import re
import subprocess
import sys
from pathlib import Path

from ccpm_scheduler import (build_schedule, load_network,
                            render_network_html)

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
    assert "My &lt;plan&gt; &amp; co" in html   # title escaped

    graph = embedded_graph(html)
    assert {n["id"] for n in graph["nodes"]} == {r.id for r in schedule.rows}
    # every parsed predecessor link becomes an edge
    assert len(graph["edges"]) == sum(
        len([t for t in r.predecessor_ids.replace(";", " ").split() if t])
        for r in schedule.rows)
    # buffer attachments render dashed, plain FS edges solid and unlabeled
    fb_edge = next(e for e in graph["edges"] if e["to"] == "FB1")
    assert fb_edge["dashes"] and "label" not in fb_edge
    fs_edge = next(e for e in graph["edges"]
                   if e["to"] == "B" and e["from"] == "A")
    assert fs_edge["dashes"] is False and "label" not in fs_edge
    # critical chain / buffers colored per the Gantt code
    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["A"]["color"]["background"] == "#b22222"
    assert by_id["PB"]["color"]["background"] == "#ffd700"
    assert by_id["PB"]["shapeProperties"]["borderDashes"] == [4, 3]
    # inspector payload carries the row data
    assert by_id["B"]["data"]["duration"] == 10
    assert by_id["B"]["data"]["resources"] == "green"
    # legend and summary present
    assert {l["label"] for l in graph["legend"]} >= \
        {"Critical chain", "Project buffer", "Feeding buffer"}
    assert "promised completion: day 45" in graph["summary"]


def test_script_injection_guarded():
    schedule = example_schedule()
    schedule.rows[0].name = "sneaky</script><script>alert(1)"
    html = render_network_html(schedule)
    # the raw terminator must not appear inside the embedded payload
    payload = html.split("const GRAPH = ", 1)[1]
    assert "</script><script>" not in payload.split("</script>")[0]


def test_zero_duration_milestone_is_diamond():
    d = DATA / "lab-trials"   # produces a FINISH milestone
    net = load_network(d / "tasks.csv", d / "resources.csv")
    schedule = build_schedule(net, title="lab").schedule
    graph = embedded_graph(render_network_html(schedule))
    finish = next(n for n in graph["nodes"] if n["id"] == "FINISH")
    assert finish["shape"] == "diamond"


def cli(*args):
    return subprocess.run([sys.executable, "-m", "ccpm_scheduler", *map(str, args)],
                          capture_output=True, text=True)


def test_cli_graph(tmp_path):
    d = DATA / "example"
    cli("build", d / "tasks.csv", d / "resources.csv",
        "--calendar", d / "calendar.csv", "--out-dir", tmp_path,
        "--title", "example")
    out = tmp_path / "project-network.html"
    r = cli("graph", tmp_path / "schedule.csv", out,
            "--title", "example", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ok"] is True
    html = out.read_text()
    assert "vis-network" in html and '"id": "PB"' in html

    # deterministic: a second render is byte-identical
    out2 = tmp_path / "again.html"
    cli("graph", tmp_path / "schedule.csv", out2, "--title", "example")
    assert out.read_bytes() == out2.read_bytes()


def test_cli_graph_missing_schedule_exit_2(tmp_path):
    r = cli("graph", tmp_path / "nope.csv", tmp_path / "out.html")
    assert r.returncode == 2
