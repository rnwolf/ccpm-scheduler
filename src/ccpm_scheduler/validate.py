"""Validate a CCPM project network BEFORE attempting to schedule.

Library API:  validate_network(network) -> ValidationReport
CLI:          python -m ccpm_scheduler.validate tasks.csv resources.csv [calendar.csv]

The project network must be logically valid. Errors (exit 1):
  - duplicate task or resource ids                        E_DUP_TASK / E_DUP_RESOURCE
  - unknown predecessor ids, malformed link tokens        E_UNKNOWN_PRED / E_MALFORMED_LINK
  - circular dependencies (the cycle is reported)         E_CYCLE
  - non-positive or non-numeric task durations            E_BAD_DURATION
  - fractional durations/capacities/allocations           E_FRACTIONAL_DURATION /
    (v1 schedules whole days and whole resources)         E_FRACTIONAL_CAPACITY /
                                                          E_FRACTIONAL_ALLOCATION
  - tasks with no resources assigned — a task without     E_NO_RESOURCE
    a resource cannot contend for capacity, so it cannot
    participate properly in critical chain identification
  - unknown resource ids on tasks                         E_UNKNOWN_RESOURCE
  - non-positive resource capacity                        E_BAD_CAPACITY
  - calendar problems: unknown resource ids, from >= to,  E_CAL_*
    overlapping ranges for the same resource, negative
    capacity, non-numeric rows

Warnings (reported, exit still 0):
  - resource capacity > 1 (unusual in CCPM)               W_CAPACITY_GT1
  - non-FS dependency links (supported; buffer sizing on  W_NON_FS_LINK
    chains with SS/FF overlaps uses elapsed span)
  - legacy column names (predecessors/resources)          W_LEGACY_COLUMNS

The report also lists the network's entry/exit points (start_tasks /
terminal_tasks). Multiple entry or exit points are fine: the scheduler
anchors them to synthetic Start/Finish milestones.

Exit code 0 = inputs valid (warnings allowed), 1 = errors found.
"""
from __future__ import annotations

import sys
from collections import defaultdict

from . import io
from .model import Network, ValidationReport


def _as_whole(value):
    """(int, None) on success; (None, 'fractional'|'bad') on failure."""
    if isinstance(value, bool):
        return None, "bad"
    if isinstance(value, int):
        return value, None
    if isinstance(value, float):
        return (int(value), None) if value.is_integer() else (None, "fractional")
    return None, "bad"


def validate_network(net: Network) -> ValidationReport:
    rep = ValidationReport()

    # ---- resources ----
    caps = {}
    for r in net.resources:
        rid = r.id
        if rid in caps:
            rep.error("E_DUP_RESOURCE", f"duplicate resource id {rid}",
                      resource_ids=[rid])
        cap, why = _as_whole(r.capacity)
        if why == "fractional":
            rep.error("E_FRACTIONAL_CAPACITY",
                      f"resource {rid}: fractional capacity {r.capacity!r} is not "
                      f"supported in v1 — use whole units and model partial "
                      f"availability with the calendar", resource_ids=[rid])
        elif why == "bad":
            rep.error("E_BAD_CAPACITY",
                      f"resource {rid}: capacity must be a number (got {r.capacity!r})",
                      resource_ids=[rid])
        elif cap < 1:
            rep.error("E_BAD_CAPACITY",
                      f"resource {rid}: capacity must be >= 1 (got {cap})",
                      resource_ids=[rid])
        elif cap > 1:
            rep.warning("W_CAPACITY_GT1",
                        f"resource {rid}: capacity {cap} > 1 is unusual in CCPM",
                        resource_ids=[rid])
        caps[rid] = cap if cap is not None else 1

    # ---- tasks ----
    ids, preds = set(), {}
    for t in net.tasks:
        if t.id in ids:
            rep.error("E_DUP_TASK", f"duplicate task id {t.id}", task_ids=[t.id])
        ids.add(t.id)
    for t in net.tasks:
        tid = t.id
        d_raw = t.optimal_duration if t.optimal_duration is not None \
            else t.realistic_duration
        d, why = _as_whole(d_raw)
        if why == "fractional":
            rep.error("E_FRACTIONAL_DURATION",
                      f"task {tid}: fractional duration {d_raw!r} is not supported "
                      f"in v1 — durations are whole working days (round up)",
                      task_ids=[tid])
        elif why == "bad" or d < 1:
            rep.error("E_BAD_DURATION",
                      f"task {tid}: duration must be a positive number of days "
                      f"(got {d_raw!r})", task_ids=[tid])
        for rid, alloc in (t.allocations or {}).items():
            if alloc != 1:
                rep.error("E_FRACTIONAL_ALLOCATION",
                          f"task {tid}: allocation {alloc} of resource {rid} is not "
                          f"supported in v1 — assign whole resources (or split "
                          f"the task)", task_ids=[tid], resource_ids=[rid])
        links = []
        for tok, link in io.iter_link_tokens(t.predecessor_notation()):
            if link is None:
                rep.error("E_MALFORMED_LINK",
                          f"task {tid}: malformed dependency link {tok!r}",
                          task_ids=[tid])
                continue
            if link.pred_id not in ids:
                rep.error("E_UNKNOWN_PRED",
                          f"task {tid}: unknown predecessor {link.pred_id}",
                          task_ids=[tid, link.pred_id])
            if link.type != "FS":
                rep.warning("W_NON_FS_LINK",
                            f"task {tid}: non-FS link {tok} (supported, but check "
                            f"buffer sizing notes)", task_ids=[tid])
            links.append(link.pred_id)
        preds[tid] = links
        if not t.resource_ids:
            rep.error("E_NO_RESOURCE",
                      f"task {tid}: no resources assigned — a task without a "
                      f"resource cannot contend for capacity and breaks critical "
                      f"chain identification", task_ids=[tid])
        for rr in t.resource_ids:
            if rr not in caps:
                rep.error("E_UNKNOWN_RESOURCE", f"task {tid}: unknown resource {rr}",
                          task_ids=[tid], resource_ids=[rr])

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
                rep.error("E_CYCLE",
                          "circular dependency: " + " -> ".join(reversed(cyc)),
                          task_ids=cyc[:-1])
                continue
            if color[pid] == WHITE:
                dfs(pid)
        stack.pop()
        color[tid] = BLACK

    for tid in preds:
        if color[tid] == WHITE:
            dfs(tid)

    # ---- calendar ----
    seen = defaultdict(list)
    for w in net.calendar:
        rid = w.resource_id
        lo, wl = _as_whole(w.start)
        hi, wh = _as_whole(w.end)
        cap, wc = _as_whole(w.capacity)
        if wl or wh or wc:
            rep.error("E_CAL_BAD_ROW",
                      f"calendar: bad row for resource {rid!r} — expected whole "
                      f"numbers for from, to, capacity (got from={w.start!r}, "
                      f"to={w.end!r}, capacity={w.capacity!r})",
                      resource_ids=[rid])
            continue
        if rid not in caps:
            rep.error("E_CAL_UNKNOWN_RESOURCE", f"calendar: unknown resource {rid}",
                      resource_ids=[rid])
            continue
        if lo >= hi:
            rep.error("E_CAL_EMPTY_RANGE",
                      f"calendar: {rid} range [{lo},{hi}) is empty or inverted",
                      resource_ids=[rid])
        if cap < 0:
            rep.error("E_CAL_NEG_CAPACITY",
                      f"calendar: {rid} capacity must be >= 0 (got {cap})",
                      resource_ids=[rid])
        for plo, phi in seen[rid]:
            if lo < phi and plo < hi:
                rep.error("E_CAL_OVERLAP",
                          f"calendar: {rid} ranges [{plo},{phi}) and [{lo},{hi}) "
                          f"overlap", resource_ids=[rid])
        seen[rid].append((lo, hi))

    # ---- structure ----
    has_succ = {p for links in preds.values() for p in links}
    rep.start_tasks = sorted(t for t in preds if not preds[t])
    rep.terminal_tasks = sorted(t for t in preds if t not in has_succ)
    return rep


def report_lines(net: Network, rep: ValidationReport):
    """Human-readable report text. Returns (lines, exit_code)."""
    lines = [f"  warning: {w.message}" for w in net.io_warnings + rep.warnings]
    if not rep.ok:
        lines.append(f"INVALID — {len(rep.errors)} error(s):")
        lines.extend(f"  - {e.message}" for e in rep.errors)
        return lines, 1
    n_resources = len({r.id for r in net.resources})
    lines.append(f"VALID — {len(net.tasks)} tasks, {n_resources} resources.")
    lines.append(f"  start tasks (no predecessors): {', '.join(rep.start_tasks) or '-'}")
    lines.append(f"  terminal tasks (no successors): {', '.join(rep.terminal_tasks) or '-'}")
    if len(rep.start_tasks) > 1:
        lines.append("  note: multiple entry points — the scheduler anchors them to one synthetic Start milestone.")
    if len(rep.terminal_tasks) > 1:
        lines.append("  note: multiple exit points — the scheduler anchors them to one synthetic Finish milestone.")
    return lines, 0


def main(tasks_path, resources_path, calendar_path=None):
    net = io.load_network(tasks_path, resources_path, calendar_path)
    lines, code = report_lines(net, validate_network(net))
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:4]))
