"""Load/save CCPM networks and schedules — CSV files (the original contract)
and a JSON exchange format for embedding tools (e.g. our-planner).

CSV input columns:
  tasks.csv     id, name, realistic_duration, optimal_duration (optional),
                predecessor_ids, resource_ids, url (optional)
                (legacy aliases accepted: duration_safe -> realistic_duration,
                duration_aggressive -> optimal_duration, duration ->
                realistic_duration, predecessors/resources -> *_ids)
  resources.csv id, name, capacity, url (optional)
  calendar.csv  resource_id, from, to, capacity   (half-open [from, to))

JSON exchange format (network_from_json / network_to_json):

    {
      "tasks": [
        {"id": "A", "name": "Spec",
         "realistic_duration": 10, "optimal_duration": null,
         "predecessors": [{"id": "B", "type": "SS", "lag": 2}],  # or "B:SS+2"
         "resources": ["blue"],           # or {"blue": 1.0} with allocations
         "url": ""}
      ],
      "resources": [{"id": "blue", "name": "Blue", "capacity": 1, "url": ""}],
      "calendar":  [{"resource_id": "green", "from": 2, "to": 4, "capacity": 0}]
    }

`predecessors` accepts the string notation, a list of tokens, or a list of
{id, type, lag} dicts (our-planner's internal shape). Task/resource ids may
be numbers in JSON; they are coerced to strings. Loading is lenient — bad
numbers etc. are kept raw for validate_network to report as issues.
"""
from __future__ import annotations

import csv
import json
import os
import re

from .model import (Link, Task, Resource, CalendarWindow, Network, Issue,
                    WARNING, Schedule, ScheduleRow, SCHEDULE_COLUMNS)

# input links: FS/SS/FF/SF only — buffer types are output-only
INPUT_LINK_RE = re.compile(
    r"^(?P<id>[^:+\s]+)(?::(?P<type>FS|SS|FF|SF))?(?P<lag>[+-]\d+)?$", re.I)
# schedule rows additionally use :PB / :FB buffer attachments
SCHED_LINK_RE = re.compile(
    r"^(?P<id>[^:+\s]+)(?::(?P<type>FS|SS|FF|SF|PB|FB))?(?P<lag>[+-]\d+)?$", re.I)

INPUT_LINK_TYPES = ("FS", "SS", "FF", "SF")


def split_tokens(s):
    """Split on semicolons, commas, and whitespace."""
    return [x for x in (s or "").replace(";", " ").replace(",", " ").split() if x]


def iter_link_tokens(s, buffer_links=False):
    """[(token, Link-or-None), ...] — None marks a malformed token."""
    rx = SCHED_LINK_RE if buffer_links else INPUT_LINK_RE
    out = []
    for tok in split_tokens(s):
        m = rx.match(tok)
        out.append((tok, Link(m.group("id"), (m.group("type") or "FS").upper(),
                              int(m.group("lag") or 0)) if m else None))
    return out


def parse_links(s, buffer_links=False):
    """Parse link notation, silently skipping malformed tokens (validation
    reports them; the engines just ignore them, as they always have)."""
    return [l for _, l in iter_link_tokens(s, buffer_links) if l is not None]


def parse_number(raw):
    """'' / None -> None; int if possible; float if numeric; else the raw
    string (validate_network reports it)."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return raw


def _first(row, *names):
    """First value whose column is present (may be '') — mirrors how the
    original scripts resolved legacy column aliases."""
    for n in names:
        if row.get(n) is not None:
            return row[n]
    return None


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        return list(r), (r.fieldnames or [])


# ---------------------------------------------------------------- CSV input

def _load_tasks(tasks_path):
    rows, cols = _read_csv(tasks_path)
    warnings = []
    for legacy, current in [("predecessors", "predecessor_ids"),
                            ("resources", "resource_ids")]:
        if legacy in cols and current not in cols:
            warnings.append(Issue(
                "W_LEGACY_COLUMNS", WARNING,
                f"tasks.csv uses legacy column '{legacy}' — rename to '{current}'"))
    tasks = []
    for t in rows:
        pred_str = _first(t, "predecessor_ids", "predecessors")
        pred_str = "" if pred_str is None else pred_str
        tasks.append(Task(
            id=t["id"],
            name=t.get("name"),
            realistic_duration=parse_number(
                _first(t, "realistic_duration", "duration_safe", "duration")),
            optimal_duration=parse_number(
                _first(t, "optimal_duration", "duration_aggressive")),
            links=parse_links(pred_str),
            resource_ids=split_tokens(_first(t, "resource_ids", "resources") or ""),
            url=t.get("url", "") or "",
            pred_str=pred_str))
    return tasks, warnings


def load_tasks(tasks_path) -> list[Task]:
    """Just the tasks from a tasks.csv — e.g. to enrich graph output with
    the duration estimates that schedule.csv doesn't carry."""
    return _load_tasks(tasks_path)[0]


def load_network(tasks_path, resources_path, calendar_path=None) -> Network:
    net = Network(has_calendar=calendar_path is not None)
    net.tasks, net.io_warnings = _load_tasks(tasks_path)
    net.resources.extend(load_resources(resources_path))
    if calendar_path:
        net.calendar.extend(load_calendar(calendar_path))
    return net


def load_resources(path) -> list[Resource]:
    return [Resource(id=r["id"], name=r.get("name"),
                     capacity=1 if r.get("capacity") in (None, "")
                     else parse_number(r.get("capacity")),
                     url=r.get("url", "") or "")
            for r in _read_csv(path)[0]]


def load_calendar(path) -> list[CalendarWindow]:
    return [CalendarWindow(resource_id=c.get("resource_id", "") or "",
                           start=parse_number(c.get("from")),
                           end=parse_number(c.get("to")),
                           capacity=parse_number(c.get("capacity")))
            for c in _read_csv(path)[0]]


# ---------------------------------------------------------------- JSON

def network_from_json(data) -> Network:
    if isinstance(data, str):
        data = json.loads(data)
    net = Network(has_calendar="calendar" in data)

    for t in data.get("tasks", []):
        tid = str(t["id"])
        preds = _first(t, "predecessors", "predecessor_ids")
        links, pred_str = [], None
        if preds is None:
            pred_str = ""
        elif isinstance(preds, str):
            pred_str = preds
            links = parse_links(preds)
        else:
            for item in preds:
                if isinstance(item, str):
                    links.extend(parse_links(item))
                else:
                    ltype = (item.get("type") or "FS").upper()
                    if ltype not in INPUT_LINK_TYPES:
                        raise ValueError(
                            f"task {tid}: link type {ltype!r} not one of "
                            f"{'/'.join(INPUT_LINK_TYPES)}")
                    links.append(Link(str(item["id"]), ltype,
                                      int(item.get("lag") or 0)))

        res = _first(t, "resources", "resource_ids")
        allocations = None
        if res is None:
            resource_ids = []
        elif isinstance(res, str):
            resource_ids = split_tokens(res)
        elif isinstance(res, dict):
            resource_ids = [str(k) for k in res]
            allocations = {str(k): float(v) for k, v in res.items()}
        else:
            resource_ids = [str(x) for x in res]

        net.tasks.append(Task(
            id=tid, name=t.get("name"),
            realistic_duration=parse_number(
                _first(t, "realistic_duration", "duration_safe", "duration")),
            optimal_duration=parse_number(
                _first(t, "optimal_duration", "duration_aggressive")),
            links=links, resource_ids=resource_ids,
            url=t.get("url", "") or "",
            allocations=allocations, pred_str=pred_str))

    for r in data.get("resources", []):
        raw_cap = r.get("capacity")
        net.resources.append(Resource(
            id=str(r["id"]), name=r.get("name"),
            capacity=1 if raw_cap in (None, "") else parse_number(raw_cap),
            url=r.get("url", "") or ""))

    for c in data.get("calendar", []):
        net.calendar.append(CalendarWindow(
            resource_id=str(c["resource_id"]),
            start=parse_number(c.get("from")),
            end=parse_number(c.get("to")),
            capacity=parse_number(c.get("capacity"))))
    return net


def network_to_json(net: Network) -> dict:
    out = {"tasks": [], "resources": []}
    for t in net.tasks:
        d = {"id": t.id, "name": t.name,
             "realistic_duration": t.realistic_duration,
             "optimal_duration": t.optimal_duration,
             "predecessors": t.predecessor_notation(),
             "resources": list(t.resource_ids),
             "url": t.url}
        if t.allocations is not None:
            d["resources"] = dict(t.allocations)
        out["tasks"].append(d)
    for r in net.resources:
        out["resources"].append({"id": r.id, "name": r.name,
                                 "capacity": r.capacity, "url": r.url})
    if net.has_calendar or net.calendar:
        out["calendar"] = [{"resource_id": w.resource_id, "from": w.start,
                            "to": w.end, "capacity": w.capacity}
                           for w in net.calendar]
    return out


# ---------------------------------------------------------------- schedules

def load_schedule(path) -> Schedule:
    rows, _ = _read_csv(path)
    return Schedule(rows=[ScheduleRow(
        id=r["id"], name=r.get("name", "") or "",
        type=r.get("type", "task") or "task",
        chain=r.get("chain", "none") or "none",
        start=int(r["start"]), finish=int(r["finish"]),
        duration=int(r["duration"]),
        realistic_duration=(int(r["realistic_duration"])
                            if r.get("realistic_duration") else None),
        resource_ids=_first(r, "resource_ids", "resources") or "",
        predecessor_ids=_first(r, "predecessor_ids", "predecessors") or "",
        url=r.get("url", "") or "") for r in rows])


def schedule_from_json(data) -> Schedule:
    if isinstance(data, str):
        data = json.loads(data)
    rows = data["rows"] if isinstance(data, dict) else data
    return Schedule(rows=[ScheduleRow(
        id=str(r["id"]), name=r.get("name", "") or "",
        type=r.get("type", "task") or "task",
        chain=r.get("chain", "none") or "none",
        start=int(r["start"]), finish=int(r["finish"]),
        duration=int(r["duration"]),
        realistic_duration=(int(r["realistic_duration"])
                            if r.get("realistic_duration") not in (None, "")
                            else None),
        resource_ids=r.get("resource_ids", "") or "",
        predecessor_ids=_first(r, "predecessor_ids", "predecessors") or "",
        url=r.get("url", "") or "") for r in rows])


def write_schedule_csv(schedule: Schedule, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SCHEDULE_COLUMNS)
        w.writeheader()
        w.writerows(r.to_csv_dict() for r in schedule.rows)


def write_build_outputs(result, out_dir):
    """Write schedule.csv + summary.md (the deliverable files)."""
    os.makedirs(out_dir, exist_ok=True)
    write_schedule_csv(result.schedule, os.path.join(out_dir, "schedule.csv"))
    with open(os.path.join(out_dir, "summary.md"), "w") as f:
        f.write(result.summary_markdown)
