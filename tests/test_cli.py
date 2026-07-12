"""CLI contract tests: exit codes, --json shapes, input flexibility.

The CLI is a contract for agents: 0 = ok, 1 = problems found (report still
emitted), 2 = usage error; --json output must stay parseable and stable.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
GOLDEN = Path(__file__).parent / "golden"


def cli(*args, stdin=None):
    return subprocess.run([sys.executable, "-m", "ccpm_scheduler", *map(str, args)],
                          capture_output=True, text=True, input=stdin)


def example_args():
    d = DATA / "example"
    return [d / "tasks.csv", d / "resources.csv", d / "calendar.csv"]


# ------------------------------------------------------------- exit codes

def test_validate_ok_exit_0():
    r = cli("validate", *example_args())
    assert r.returncode == 0 and r.stdout.startswith("VALID")


def test_validate_errors_exit_1(tmp_path):
    (tmp_path / "tasks.csv").write_text(
        "id,name,realistic_duration,predecessor_ids,resource_ids\n"
        "A,A,4,B,r1\nB,B,4,A,r1\n")
    (tmp_path / "resources.csv").write_text("id,name,capacity\nr1,R,1\n")
    r = cli("validate", tmp_path / "tasks.csv", tmp_path / "resources.csv")
    assert r.returncode == 1 and "INVALID" in r.stdout


def test_usage_error_exit_2():
    assert cli("validate").returncode == 2
    assert cli("frobnicate").returncode == 2
    assert cli("build", "only-one.csv", "two.csv", "three.csv", "four.csv"
               ).returncode == 2


def test_missing_file_exit_2(tmp_path):
    r = cli("validate", tmp_path / "nope.csv", tmp_path / "nada.csv")
    assert r.returncode == 2 and "cannot read" in r.stderr


# ------------------------------------------------------------- --json

def test_validate_json_shape(tmp_path):
    (tmp_path / "tasks.csv").write_text(
        "id,name,realistic_duration,predecessor_ids,resource_ids\n"
        "A,A,4,B,r1\nB,B,4,A,\n")
    (tmp_path / "resources.csv").write_text("id,name,capacity\nr1,R,2\n")
    r = cli("validate", tmp_path / "tasks.csv", tmp_path / "resources.csv",
            "--json")
    assert r.returncode == 1
    j = json.loads(r.stdout)
    assert j["ok"] is False
    codes = {i["code"] for i in j["issues"]}
    assert {"E_CYCLE", "E_NO_RESOURCE", "W_CAPACITY_GT1"} <= codes
    assert j["errors"] >= 2 and j["warnings"] >= 1


def test_build_json_and_files(tmp_path):
    out = tmp_path / "plan"
    r = cli("build", *example_args()[:2], "--calendar", example_args()[2],
            "--out-dir", out, "--title", "example", "--json")
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["ok"] is True
    assert j["stats"]["critical_chain"] == ["A", "B", "D", "F"]
    assert j["stats"]["promise_day"] == 45
    ids = [row["id"] for row in j["schedule"]["rows"]]
    assert "PB" in ids
    # files written and byte-identical to the goldens
    assert (out / "schedule.csv").read_bytes() == \
        (GOLDEN / "example" / "schedule.csv").read_bytes()
    assert (out / "summary.md").exists()


def test_build_validates_first(tmp_path):
    (tmp_path / "tasks.csv").write_text(
        "id,name,realistic_duration,predecessor_ids,resource_ids\n"
        "A,A,4,GHOST,r1\n")
    (tmp_path / "resources.csv").write_text("id,name,capacity\nr1,R,1\n")
    r = cli("build", tmp_path / "tasks.csv", tmp_path / "resources.csv",
            "--out-dir", tmp_path, "--json")
    assert r.returncode == 1
    j = json.loads(r.stdout)
    assert j["ok"] is False
    assert "E_UNKNOWN_PRED" in {i["code"] for i in j["issues"]}
    assert not (tmp_path / "schedule.csv").exists()


# ------------------------------------------------------------- JSON input

NETWORK_JSON = json.dumps({
    "tasks": [
        {"id": 1, "name": "Spec", "realistic_duration": 10,
         "predecessors": [], "resources": {"1": 1.0}},
        {"id": 2, "name": "Build", "realistic_duration": 20,
         "predecessors": [{"id": 1, "type": "FS", "lag": 0}],
         "resources": {"1": 1.0}},
    ],
    "resources": [{"id": 1, "name": "Dev"}],
})


def test_build_from_json_stdin(tmp_path):
    r = cli("build", "-", "--out-dir", tmp_path, "--title", "mini", "--json",
            stdin=NETWORK_JSON)
    assert r.returncode == 0, r.stderr
    j = json.loads(r.stdout)
    assert j["ok"] and j["stats"]["critical_chain"] == ["1", "2"]
    assert (tmp_path / "schedule.csv").exists()


def test_validate_json_file_input(tmp_path):
    p = tmp_path / "net.json"
    p.write_text(NETWORK_JSON)
    r = cli("validate", p, "--json")
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is True


def test_json_input_rejects_calendar_flag(tmp_path):
    p = tmp_path / "net.json"
    p.write_text(NETWORK_JSON)
    r = cli("validate", p, "--calendar", "cal.csv")
    assert r.returncode == 2


def test_bad_json_exit_2():
    r = cli("validate", "-", stdin="{not json")
    assert r.returncode == 2 and "bad JSON" in r.stderr


# ------------------------------------------------------------- check / plot

def test_check_roundtrip(tmp_path):
    cli("build", *example_args()[:2], "--calendar", example_args()[2],
        "--out-dir", tmp_path, "--title", "example")
    r = cli("check", tmp_path / "schedule.csv", *example_args())
    assert r.returncode == 0 and "VALID" in r.stdout


def test_check_catches_violation_json(tmp_path):
    cli("build", *example_args()[:2], "--calendar", example_args()[2],
        "--out-dir", tmp_path, "--title", "example")
    sched = (tmp_path / "schedule.csv").read_text().replace(
        "PB,Project buffer,project_buffer,critical,30,45,15",
        "PB,Project buffer,project_buffer,critical,29,44,15")
    (tmp_path / "schedule.csv").write_text(sched)
    r = cli("check", tmp_path / "schedule.csv", *example_args(), "--json")
    assert r.returncode == 1
    j = json.loads(r.stdout)
    assert "E_PB_PLACEMENT" in {i["code"] for i in j["issues"]}


def test_plot_json(tmp_path):
    cli("build", *example_args()[:2], "--calendar", example_args()[2],
        "--out-dir", tmp_path, "--title", "example")
    png = tmp_path / "g.png"
    r = cli("plot", tmp_path / "schedule.csv", png,
            "--resources", example_args()[1], "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["ok"] is True
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


# ------------------------------------------------------------- schema / meta

@pytest.mark.parametrize("which", ["network", "schedule", "report"])
def test_schema_emits_json_schema(which):
    r = cli("schema", which)
    assert r.returncode == 0
    j = json.loads(r.stdout)
    assert j["$schema"].startswith("https://json-schema.org/")
    assert "properties" in j


def test_schema_default_is_network():
    assert "CCPM project network" in json.loads(cli("schema").stdout)["title"]


def test_version():
    r = cli("--version")
    assert r.returncode == 0 and r.stdout.startswith("ccpm-scheduler ")


def test_console_script_installed():
    r = subprocess.run(["ccpm-scheduler", "--version"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("ccpm-scheduler ")


def test_build_deterministic_stdout(tmp_path):
    a = cli("build", *example_args()[:2], "--calendar", example_args()[2],
            "--out-dir", tmp_path / "a", "--title", "example", "--json")
    b = cli("build", *example_args()[:2], "--calendar", example_args()[2],
            "--out-dir", tmp_path / "b", "--title", "example", "--json")
    ja, jb = json.loads(a.stdout), json.loads(b.stdout)
    del ja["files"], jb["files"]
    assert ja == jb
