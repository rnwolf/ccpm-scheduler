"""Validate CCPM input files BEFORE attempting to schedule.

Usage: uv run validate_inputs.py tasks.csv resources.csv [calendar.csv]

The project network must be logically valid. Errors (exit 1):
  - duplicate task or resource ids
  - unknown predecessor ids, malformed link tokens
  - circular dependencies (the cycle is reported)
  - non-positive task durations (every task must take at least 1 day)
  - tasks with no resources assigned — a task without a resource cannot
    contend for capacity, so it cannot participate properly in critical
    chain identification or leveling
  - non-positive resource capacity
  - calendar problems: unknown resource ids, from >= to, overlapping
    ranges for the same resource, negative capacity

Warnings (reported, exit still 0):
  - resource capacity > 1 (supported, but unusual in CCPM)
  - non-FS dependency links (supported; buffer sizing on chains with
    SS/FF overlaps uses elapsed span, see references/algorithm.md)
  - legacy column names (predecessors/resources) — rename to
    predecessor_ids/resource_ids

Structure report (informational): the start tasks (no predecessors) and
terminal tasks (no successors). Multiple entry or exit points are fine:
the scheduler anchors them to a single synthetic Start milestone and a
single synthetic Finish milestone (zero duration, no resources, removed
from outputs), so the network always flows one source to one sink.

Column names: `predecessor_ids` and `resource_ids` (legacy
`predecessors`/`resources` accepted with a warning).

Exit code 0 = inputs valid (warnings allowed), 1 = errors found.
"""
import csv
import re
import sys
from collections import defaultdict

LINK_RE = re.compile(r"^(?P<id>[^:+\s]+)(?::(?P<type>FS|SS|FF|SF))?(?P<lag>[+-]\d+)?$", re.I)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f)), csv.DictReader(open(path)).fieldnames


def field(row, *names):
    for n in names:
        if row.get(n) is not None:
            return row[n]
    return ""


def main(tasks_path, resources_path, calendar_path=None):
    errors, warnings = [], []

    tasks, task_cols = read_csv(tasks_path)
    resources, res_cols = read_csv(resources_path)
    for legacy, current, cols in [("predecessors", "predecessor_ids", task_cols),
                                  ("resources", "resource_ids", task_cols)]:
        if cols and legacy in cols and current not in cols:
            warnings.append(f"tasks.csv uses legacy column '{legacy}' — rename to '{current}'")

    # ---- resources ----
    caps = {}
    for r in resources:
        rid = r["id"]
        if rid in caps:
            errors.append(f"duplicate resource id {rid}")
        cap = int(r.get("capacity") or 1)
        if cap < 1:
            errors.append(f"resource {rid}: capacity must be >= 1 (got {cap})")
        elif cap > 1:
            warnings.append(f"resource {rid}: capacity {cap} > 1 is unusual in CCPM")
        caps[rid] = cap

    # ---- tasks ----
    ids, preds = set(), {}
    for t in tasks:
        tid = t["id"]
        if tid in ids:
            errors.append(f"duplicate task id {tid}")
        ids.add(tid)
    for t in tasks:
        tid = t["id"]
        d_raw = (t.get("optimal_duration") or t.get("realistic_duration")
                 or t.get("duration_aggressive") or t.get("duration_safe") or t.get("duration"))
        try:
            if d_raw is None or int(d_raw) < 1:
                errors.append(f"task {tid}: duration must be a positive number of days (got {d_raw!r})")
        except ValueError:
            errors.append(f"task {tid}: duration must be a positive number of days (got {d_raw!r})")
        links = []
        for tok in field(t, "predecessor_ids", "predecessors").replace(";", " ").replace(",", " ").split():
            m = LINK_RE.match(tok)
            if not m:
                errors.append(f"task {tid}: malformed dependency link {tok!r}")
                continue
            pid, ltype = m.group("id"), (m.group("type") or "FS").upper()
            if pid not in ids:
                errors.append(f"task {tid}: unknown predecessor {pid}")
            if ltype != "FS":
                warnings.append(f"task {tid}: non-FS link {tok} (supported, but check buffer sizing notes)")
            links.append(pid)
        preds[tid] = links
        res = [x for x in field(t, "resource_ids", "resources").replace(";", " ").replace(",", " ").split() if x]
        if not res:
            errors.append(f"task {tid}: no resources assigned — a task without a resource "
                          f"cannot contend for capacity and breaks critical chain identification")
        for rr in res:
            if rr not in caps:
                errors.append(f"task {tid}: unknown resource {rr}")

    # ---- cycles ----
    WHITE, GREY, BLACK = 0, 1, 2
    color, stack = defaultdict(int), []
    def dfs(tid):
        color[tid] = GREY
        stack.append(tid)
        for pid in preds.get(tid, ()):
            if pid not in preds:
                continue
            if color[pid] == GREY:
                cyc = stack[stack.index(pid):] + [pid]
                errors.append("circular dependency: " + " -> ".join(reversed(cyc)))
                continue
            if color[pid] == WHITE:
                dfs(pid)
        stack.pop()
        color[tid] = BLACK
    for tid in preds:
        if color[tid] == WHITE:
            dfs(tid)

    # ---- calendar ----
    if calendar_path:
        cal_rows, _ = read_csv(calendar_path)
        seen = defaultdict(list)
        for c in cal_rows:
            rid = c.get("resource_id", "")
            try:
                lo, hi, cap = int(c["from"]), int(c["to"]), int(c["capacity"])
            except (KeyError, ValueError):
                errors.append(f"calendar: bad row {c} — expected resource_id, from, to, capacity")
                continue
            if rid not in caps:
                errors.append(f"calendar: unknown resource {rid}")
                continue
            if lo >= hi:
                errors.append(f"calendar: {rid} range [{lo},{hi}) is empty or inverted")
            if cap < 0:
                errors.append(f"calendar: {rid} capacity must be >= 0 (got {cap})")
            for plo, phi in seen[rid]:
                if lo < phi and plo < hi:
                    errors.append(f"calendar: {rid} ranges [{plo},{phi}) and [{lo},{hi}) overlap")
            seen[rid].append((lo, hi))

    # ---- structure report ----
    has_succ = {p for links in preds.values() for p in links}
    starts = sorted(t for t in preds if not preds[t])
    sinks = sorted(t for t in preds if t not in has_succ)

    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print(f"INVALID — {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"VALID — {len(tasks)} tasks, {len(caps)} resources.")
    print(f"  start tasks (no predecessors): {', '.join(starts) or '-'}")
    print(f"  terminal tasks (no successors): {', '.join(sinks) or '-'}")
    if len(starts) > 1:
        print("  note: multiple entry points — the scheduler anchors them to one synthetic Start milestone.")
    if len(sinks) > 1:
        print("  note: multiple exit points — the scheduler anchors them to one synthetic Finish milestone.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
