"""Verify a produced CCPM schedule against the input network.

Library API:  check_schedule(schedule, network) -> ValidationReport
CLI:          python -m ccpm_scheduler.check schedule.csv tasks.csv resources.csv
                  [calendar.csv]

Checks (issue codes in brackets):
  1. Every input task appears exactly once in the schedule.
     [E_MISSING_TASK, E_DUP_ROW]
  2. finish == start + duration for every row. [E_ARITHMETIC]
  3. Precedence per link type (FS default): FS pred.finish+lag <= start;
     SS pred.start+lag <= start; FF pred.finish+lag <= finish;
     SF pred.start+lag <= finish. Notation: A, A:SS, A:FF+2, A:SF-1.
     [E_LINK_VIOLATION, E_UNKNOWN_PRED]
  4. Resource capacity never exceeded on any day. With a calendar, the
     effective per-day capacity is used; tasks run contiguously (they never
     split), so a task spanning a zero-capacity day of one of its resources
     is a violation. [E_OVERLOAD, E_UNKNOWN_RESOURCE]
  5. Exactly one project buffer, placed at the end of the critical chain,
     with exactly ONE predecessor: the terminal critical-chain task, via a
     :PB link. Feeding chains never merge into the project buffer — chains
     that run to the project end merge into a zero-duration Finish
     milestone on the critical chain, and the PB hangs off that milestone.
     [E_PB_COUNT, E_PB_PLACEMENT, E_PB_PRED]
  6. Each feeding buffer starts exactly where the task it attaches to (its
     single :FB predecessor) finishes, and its END lands exactly on the
     start of a critical-chain task (the protected join point).
     [E_FB_ATTACH, E_FB_ANCHOR]
  7. No negative starts. [E_NEG_START]
  8. Buffer link discipline: buffer rows attach via :PB / :FB links (not
     plain FS); a :FB link is only legal when one end is a feeding buffer;
     a feeding buffer's outgoing merge may target only a critical-chain
     TASK (never another buffer); buffers consume no resources. Buffers
     are not work - during execution their end stays anchored and slippage
     consumes them, so the type must be explicit.
     [E_BUFFER_LINK, E_BUFFER_RESOURCES]
  9. Calendar sanity: known resource ids, from < to, no overlapping ranges
     for the same resource. [E_CAL_*]
 10. Every buffer is at least 1 day long. A zero-length buffer protects
     nothing — if a feeding chain has no room for its buffer, the schedule
     should omit the buffer and flag the chain instead. [E_ZERO_BUFFER]
 11. Every feeding buffer MERGES: exactly one row lists it as a predecessor
     via `<FBid>:FB`, and that successor is a critical-chain task.
     A buffer with no successor dangles outside the network. [E_FB_MERGE]
 12. No bypasses or unbuffered merges: a non-critical task must not feed a
     critical-chain task directly when a feeding buffer covers (or could
     cover) that merge — the direct edge must be REROUTED through the
     buffer. A direct edge is accepted only when there is zero room for a
     buffer (the flagged effectively-critical case).
     [E_BYPASS, E_UNBUFFERED_MERGE]

Exit code 0 = valid, 1 = violations found (printed to stdout).
"""
from __future__ import annotations

import sys
from collections import defaultdict

from . import io
from .model import Network, Schedule, ValidationReport, as_int


def _parse_links(s):
    return [(l.pred_id, l.type, l.lag) for l in io.parse_links(s, buffer_links=True)]


def check_schedule(schedule: Schedule, network: Network) -> ValidationReport:
    rep = ValidationReport()
    err = rep.error
    sched = schedule.rows
    tasks = {t.id: t for t in network.tasks}
    resources = {}
    for r in network.resources:
        try:
            resources[r.id] = as_int(r.capacity)
        except ValueError:
            err("E_BAD_CAPACITY",
                f"resource {r.id}: capacity is not a whole number ({r.capacity!r})",
                resource_ids=[r.id])
            resources[r.id] = 1

    # 9. calendar overrides: resource -> [(from, to, capacity)]
    overrides = defaultdict(list)
    for w in network.calendar:
        try:
            res, lo, hi, cap = (w.resource_id, as_int(w.start),
                                as_int(w.end), as_int(w.capacity))
        except ValueError:
            err("E_CAL_BAD_ROW",
                f"calendar: bad row for resource {w.resource_id!r} — expected "
                f"whole numbers for from, to, capacity",
                resource_ids=[w.resource_id])
            continue
        if res not in resources:
            err("E_CAL_UNKNOWN_RESOURCE", f"calendar: unknown resource {res}",
                resource_ids=[res])
            continue
        if lo >= hi:
            err("E_CAL_EMPTY_RANGE",
                f"calendar: {res} range [{lo},{hi}) is empty or inverted",
                resource_ids=[res])
            continue
        for plo, phi, _ in overrides[res]:
            if lo < phi and plo < hi:
                err("E_CAL_OVERLAP",
                    f"calendar: {res} ranges [{plo},{phi}) and [{lo},{hi}) overlap",
                    resource_ids=[res])
        overrides[res].append((lo, hi, cap))

    def cap_on(res, day):
        for lo, hi, cap in overrides.get(res, ()):
            if lo <= day < hi:
                return cap
        return resources[res]

    rows = {}
    for r in sched:
        if r.id in rows:
            err("E_DUP_ROW", f"duplicate schedule row id {r.id}", task_ids=[r.id])
        rows[r.id] = r

    # 1. coverage
    for tid in tasks:
        if tid not in rows:
            err("E_MISSING_TASK", f"task {tid} missing from schedule",
                task_ids=[tid])
    # 2. arithmetic & 7. negative starts
    for r in sched:
        if r.finish != r.start + r.duration:
            err("E_ARITHMETIC", f"{r.id}: finish != start + duration",
                task_ids=[r.id])
        if r.start < 0:
            err("E_NEG_START", f"{r.id}: negative start {r.start}",
                task_ids=[r.id])

    # 3. precedence, by link type (prefer the schedule's own predecessors
    # column so buffers and normalized links are checked too)
    BOUNDS = {  # (pred attr, succ attr); PB/FB anchor like FS at plan time
        "FS": ("finish", "start"), "SS": ("start", "start"),
        "FF": ("finish", "finish"), "SF": ("start", "finish"),
        "PB": ("finish", "start"), "FB": ("finish", "start"),
    }
    BUFFER_LINK = {"project_buffer": "PB", "feeding_buffer": "FB"}
    for tid, r in rows.items():
        pred_spec = r.predecessor_ids
        if not pred_spec and tid in tasks:
            pred_spec = tasks[tid].predecessor_notation()
        for pid, ltype, lag in _parse_links(pred_spec or ""):
            if pid not in rows:
                err("E_UNKNOWN_PRED", f"{tid}: unknown predecessor {pid}",
                    task_ids=[tid, pid])
                continue
            pa, sa = BOUNDS[ltype]
            if getattr(rows[pid], pa) + lag > getattr(r, sa):
                err("E_LINK_VIOLATION",
                    f"{ltype} link violated: {pid}.{pa}={getattr(rows[pid], pa)}"
                    f"{lag:+d} > {tid}.{sa}={getattr(r, sa)}",
                    task_ids=[tid, pid])
            # 8. buffer link discipline
            expected = BUFFER_LINK.get(r.type)
            pred_is_fb = rows[pid].type == "feeding_buffer"
            if expected and not pred_is_fb and ltype != expected:
                err("E_BUFFER_LINK",
                    f"{tid}: buffer must attach via :{expected} link, got {ltype}",
                    task_ids=[tid, pid])
            if pred_is_fb and ltype != "FB":
                err("E_BUFFER_LINK",
                    f"{tid}: link from feeding buffer {pid} must use :FB, got {ltype}",
                    task_ids=[tid, pid])
            if pred_is_fb and r.type != "task":
                err("E_BUFFER_LINK",
                    f"{tid}: feeding buffer {pid} must merge into a critical-chain "
                    f"task, not a {r.type} — chains that run to the project end "
                    f"merge into a zero-duration Finish milestone",
                    task_ids=[tid, pid])
            if ltype == "FB" and not (r.type == "feeding_buffer" or pred_is_fb):
                err("E_BUFFER_LINK", f"{tid}: :FB link must involve a feeding buffer",
                    task_ids=[tid, pid])
            if ltype == "PB" and r.type != "project_buffer":
                err("E_BUFFER_LINK", f"{tid}: :PB link used on a non-project-buffer row",
                    task_ids=[tid, pid])

    # 4. resource capacity (day-by-day, calendar-aware)
    usage = defaultdict(lambda: defaultdict(int))  # resource -> day -> demand
    for r in sched:
        if r.type != "task":
            continue
        for res in io.split_tokens(r.resource_ids):
            if res not in resources:
                err("E_UNKNOWN_RESOURCE", f"{r.id}: unknown resource {res}",
                    task_ids=[r.id], resource_ids=[res])
                continue
            for day in range(r.start, r.finish):
                usage[res][day] += 1
    for res, days in usage.items():
        for day, demand in sorted(days.items()):
            cap = cap_on(res, day)
            if demand > cap:
                what = "unavailable" if cap == 0 else "over capacity"
                err("E_OVERLOAD",
                    f"resource {res} {what} on day {day} ({demand} > {cap})",
                    resource_ids=[res])
                break  # one report per resource is enough

    # 5. project buffer
    pbs = [r for r in sched if r.type == "project_buffer"]
    if len(pbs) != 1:
        err("E_PB_COUNT", f"expected exactly 1 project buffer, found {len(pbs)}")
    else:
        cc_tasks = [r for r in sched if r.type == "task" and r.chain == "critical"]
        if cc_tasks:
            last_cc = max(r.finish for r in cc_tasks)
            if pbs[0].start != last_cc:
                err("E_PB_PLACEMENT",
                    f"project buffer starts {pbs[0].start}, last critical task "
                    f"finishes {last_cc}", task_ids=[pbs[0].id])
        pb_links = _parse_links(pbs[0].predecessor_ids)
        if len(pb_links) != 1 or pb_links[0][1] != "PB" or (
                pb_links[0][0] in rows
                and not (rows[pb_links[0][0]].type == "task"
                         and rows[pb_links[0][0]].chain == "critical")):
            err("E_PB_PRED",
                f"{pbs[0].id}: project buffer must have exactly one "
                f"predecessor — the terminal critical-chain task via :PB "
                f"(got {pbs[0].predecessor_ids or 'none'})", task_ids=[pbs[0].id])

    # 8. buffers consume no resources
    for r in sched:
        if r.type in BUFFER_LINK and r.resource_ids.strip():
            err("E_BUFFER_RESOURCES", f"{r.id}: buffer must not consume resources",
                task_ids=[r.id])

    # 10. buffers have positive length
    for r in sched:
        if r.type in BUFFER_LINK and r.duration < 1:
            err("E_ZERO_BUFFER",
                f"{r.id}: zero-length buffer (duration {r.duration}) "
                f"protects nothing — omit it and flag the chain instead",
                task_ids=[r.id])

    # 11. every feeding buffer merges into exactly one protected successor
    fb_ids = {r.id for r in sched if r.type == "feeding_buffer"}
    merged = defaultdict(list)
    for tid, r in rows.items():
        for pid, ltype, lag in _parse_links(r.predecessor_ids):
            if pid in fb_ids and ltype == "FB":
                merged[pid].append(tid)
    for fb in sorted(fb_ids):
        succs = merged.get(fb, [])
        if len(succs) != 1:
            err("E_FB_MERGE",
                f"{fb}: feeding buffer must merge into exactly one successor "
                f"via a :FB link (found {len(succs)}) — a buffer without a "
                f"successor dangles outside the network", task_ids=[fb])
            continue
        s = rows[succs[0]]
        if not (s.type == "task" and s.chain == "critical"):
            err("E_FB_MERGE",
                f"{fb}: merge successor {succs[0]} must be a critical-chain task",
                task_ids=[fb, succs[0]])

    # 12. no bypasses, no unbuffered merges into the critical chain
    fb_attach_of = {}  # attach task id -> (fb id, fb finish)
    for r in sched:
        if r.type != "feeding_buffer":
            continue
        for pid, ltype, _ in _parse_links(r.predecessor_ids):
            if ltype == "FB":
                fb_attach_of[pid] = (r.id, r.finish)
    for tid, r in rows.items():
        if r.type != "task" or r.chain != "critical":
            continue
        for pid, ltype, lag in _parse_links(r.predecessor_ids):
            p = rows.get(pid)
            if not p or p.type != "task" or p.chain == "critical":
                continue
            # a non-critical task feeds this critical task directly
            if pid in fb_attach_of and fb_attach_of[pid][1] == r.start:
                err("E_BYPASS",
                    f"{tid}: direct link from {pid} BYPASSES feeding buffer "
                    f"{fb_attach_of[pid][0]} — reroute the edge through the buffer",
                    task_ids=[tid, pid])
            elif r.start - p.finish >= 1:
                err("E_UNBUFFERED_MERGE",
                    f"{tid}: unbuffered merge — non-critical {pid} feeds the "
                    f"critical chain directly with room for a feeding buffer",
                    task_ids=[tid, pid])

    # 6. feeding buffer positioning: starts at its attach task's finish,
    # ends exactly on a critical-chain task's start
    cc_starts = {r.start for r in sched if r.type == "task" and r.chain == "critical"}
    for fb in (r for r in sched if r.type == "feeding_buffer"):
        own = _parse_links(fb.predecessor_ids)
        fb_attach = [pid for pid, lt, _ in own if lt == "FB"]
        if len(own) != 1 or len(fb_attach) != 1:
            err("E_FB_ATTACH",
                f"{fb.id}: feeding buffer must attach to exactly one "
                f"task via :FB (got {fb.predecessor_ids or 'none'})",
                task_ids=[fb.id])
        elif fb_attach[0] in rows and rows[fb_attach[0]].finish != fb.start:
            err("E_FB_ATTACH",
                f"{fb.id}: starts {fb.start} but its attach task "
                f"{fb_attach[0]} finishes {rows[fb_attach[0]].finish}",
                task_ids=[fb.id, fb_attach[0]])
        if fb.finish not in cc_starts:
            err("E_FB_ANCHOR",
                f"{fb.id}: end {fb.finish} not anchored to a critical-chain "
                f"task start (its protected successor)", task_ids=[fb.id])

    return rep


def main(schedule_path, tasks_path, resources_path, calendar_path=None):
    schedule = io.load_schedule(schedule_path)
    network = io.load_network(tasks_path, resources_path, calendar_path)
    rep = check_schedule(schedule, network)
    if not rep.ok:
        print(f"INVALID — {len(rep.errors)} violation(s):")
        for e in rep.errors:
            print(f"  - {e.message}")
        return 1
    print("VALID — all checks passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:5]))
