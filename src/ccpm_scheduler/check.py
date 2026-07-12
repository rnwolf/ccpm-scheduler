"""Validate a CCPM schedule.csv against tasks.csv and resources.csv.

Usage: uv run validate_schedule.py schedule.csv tasks.csv resources.csv [calendar.csv]

Column names: `predecessor_ids` and `resource_ids` (the legacy names
`predecessors` / `resources` are also accepted).

Checks:
  1. Every input task appears exactly once in the schedule.
  2. finish == start + duration for every row.
  3. Precedence per link type (FS default): FS pred.finish+lag <= start;
     SS pred.start+lag <= start; FF pred.finish+lag <= finish;
     SF pred.start+lag <= finish. Notation: A, A:SS, A:FF+2, A:SF-1.
  4. Resource capacity never exceeded on any day. With a calendar, the
     effective per-day capacity is used; tasks run contiguously (they never
     split), so a task spanning a zero-capacity day of one of its resources
     is a violation.
  5. Exactly one project buffer, placed at the end of the critical chain,
     with exactly ONE predecessor: the terminal critical-chain task, via a
     :PB link. Feeding chains never merge into the project buffer — chains
     that run to the project end merge into a zero-duration Finish
     milestone on the critical chain, and the PB hangs off that milestone.
  6. Each feeding buffer starts exactly where the task it attaches to (its
     single :FB predecessor) finishes, and its END lands exactly on the
     start of a critical-chain task (the protected join point).
  7. No negative starts.
  8. Buffer link discipline: buffer rows attach via :PB / :FB links (not
     plain FS); a :FB link is only legal when one end is a feeding buffer;
     a feeding buffer's outgoing merge may target only a critical-chain
     TASK (never another buffer); buffers consume no resources. Buffers
     are not work - during execution their end stays anchored and slippage
     consumes them, so the type must be explicit.
  9. Calendar sanity (if calendar.csv given): known resource ids, from < to,
     no overlapping ranges for the same resource. Rows are
     `resource_id, from, to, capacity` overriding capacity on [from, to).
 10. Every buffer is at least 1 day long. A zero-length buffer protects
     nothing — if a feeding chain has no room for its buffer, the schedule
     should omit the buffer and flag the chain instead of emitting a
     zero-day row.
 11. Every feeding buffer MERGES: exactly one row lists it as a predecessor
     via `<FBid>:FB`, and that successor is a critical-chain task.
     A buffer with no successor dangles outside the network.
 12. No bypasses or unbuffered merges: a non-critical task must not feed a
     critical-chain task directly when a feeding buffer covers (or could
     cover) that merge — the direct edge must be REROUTED through the
     buffer, otherwise feeder slippage pushes the critical chain
     immediately and the buffer absorbs nothing. A direct edge is accepted
     only when there is zero room for a buffer (the flagged
     effectively-critical case).

Exit code 0 = valid, 1 = violations found (printed to stdout).
"""
import csv
import re
import sys
from collections import defaultdict

LINK_RE = re.compile(r"^(?P<id>[^:+\s]+)(?::(?P<type>FS|SS|FF|SF|PB|FB))?(?P<lag>[+-]\d+)?$", re.I)


def parse_links(s):
    """'A;B:SS+2' -> [('A','FS',0), ('B','SS',2)]"""
    out = []
    for tok in (s or "").replace(";", " ").replace(",", " ").split():
        m = LINK_RE.match(tok)
        if m:
            out.append((m.group("id"), (m.group("type") or "FS").upper(),
                        int(m.group("lag") or 0)))
    return out


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def split_ids(s):
    return [x for x in s.replace(";", " ").replace(",", " ").split() if x]


def field(row, *names):
    """First present value among column names (new name first, legacy after)."""
    for n in names:
        if row.get(n) is not None:
            return row[n]
    return ""


def main(schedule_path, tasks_path, resources_path, calendar_path=None):
    sched = read_csv(schedule_path)
    tasks = {t["id"]: t for t in read_csv(tasks_path)}
    resources = {r["id"]: int(r.get("capacity") or 1) for r in read_csv(resources_path)}
    errors = []

    # 9. calendar overrides: resource -> [(from, to, capacity)]
    overrides = defaultdict(list)
    if calendar_path:
        for c in read_csv(calendar_path):
            res, lo, hi, cap = c["resource_id"], int(c["from"]), int(c["to"]), int(c["capacity"])
            if res not in resources:
                errors.append(f"calendar: unknown resource {res}")
                continue
            if lo >= hi:
                errors.append(f"calendar: {res} range [{lo},{hi}) is empty or inverted")
                continue
            for plo, phi, _ in overrides[res]:
                if lo < phi and plo < hi:
                    errors.append(f"calendar: {res} ranges [{plo},{phi}) and [{lo},{hi}) overlap")
            overrides[res].append((lo, hi, cap))

    def cap_on(res, day):
        for lo, hi, cap in overrides.get(res, ()):
            if lo <= day < hi:
                return cap
        return resources[res]

    rows = {}
    for r in sched:
        r["start"], r["finish"], r["duration"] = int(r["start"]), int(r["finish"]), int(r["duration"])
        if r["id"] in rows:
            errors.append(f"duplicate schedule row id {r['id']}")
        rows[r["id"]] = r

    # 1. coverage
    for tid in tasks:
        if tid not in rows:
            errors.append(f"task {tid} missing from schedule")
    # 2. arithmetic & 7. negative starts
    for r in sched:
        if r["finish"] != r["start"] + r["duration"]:
            errors.append(f"{r['id']}: finish != start + duration")
        if r["start"] < 0:
            errors.append(f"{r['id']}: negative start {r['start']}")

    # 3. precedence, by link type (prefer the schedule's own predecessors
    # column so buffers and normalized links are checked too)
    BOUNDS = {  # (pred attr, succ attr); PB/FB anchor like FS at plan time
        "FS": ("finish", "start"), "SS": ("start", "start"),
        "FF": ("finish", "finish"), "SF": ("start", "finish"),
        "PB": ("finish", "start"), "FB": ("finish", "start"),
    }
    BUFFER_LINK = {"project_buffer": "PB", "feeding_buffer": "FB"}
    for tid, r in rows.items():
        pred_spec = field(r, "predecessor_ids", "predecessors")
        if not pred_spec and tid in tasks:
            pred_spec = field(tasks[tid], "predecessor_ids", "predecessors")
        for pid, ltype, lag in parse_links(pred_spec or ""):
            if pid not in rows:
                errors.append(f"{tid}: unknown predecessor {pid}")
                continue
            pa, sa = BOUNDS[ltype]
            if rows[pid][pa] + lag > r[sa]:
                errors.append(
                    f"{ltype} link violated: {pid}.{pa}={rows[pid][pa]}{lag:+d} "
                    f"> {tid}.{sa}={r[sa]}")
            # 8. buffer link discipline
            expected = BUFFER_LINK.get(r["type"])
            pred_is_fb = rows[pid]["type"] == "feeding_buffer"
            if expected and not pred_is_fb and ltype != expected:
                errors.append(f"{tid}: buffer must attach via :{expected} link, got {ltype}")
            if pred_is_fb and ltype != "FB":
                errors.append(f"{tid}: link from feeding buffer {pid} must use :FB, got {ltype}")
            if pred_is_fb and r["type"] != "task":
                errors.append(f"{tid}: feeding buffer {pid} must merge into a critical-chain "
                              f"task, not a {r['type']} — chains that run to the project end "
                              f"merge into a zero-duration Finish milestone")
            if ltype == "FB" and not (r["type"] == "feeding_buffer" or pred_is_fb):
                errors.append(f"{tid}: :FB link must involve a feeding buffer")
            if ltype == "PB" and r["type"] != "project_buffer":
                errors.append(f"{tid}: :PB link used on a non-project-buffer row")

    # 4. resource capacity (day-by-day, calendar-aware)
    usage = defaultdict(lambda: defaultdict(int))  # resource -> day -> demand
    for r in sched:
        if r["type"] != "task":
            continue
        for res in split_ids(field(r, "resource_ids", "resources")):
            if res not in resources:
                errors.append(f"{r['id']}: unknown resource {res}")
                continue
            for day in range(r["start"], r["finish"]):
                usage[res][day] += 1
    for res, days in usage.items():
        for day, demand in sorted(days.items()):
            cap = cap_on(res, day)
            if demand > cap:
                what = "unavailable" if cap == 0 else "over capacity"
                errors.append(f"resource {res} {what} on day {day} ({demand} > {cap})")
                break  # one report per resource is enough

    # 5. project buffer
    pbs = [r for r in sched if r["type"] == "project_buffer"]
    if len(pbs) != 1:
        errors.append(f"expected exactly 1 project buffer, found {len(pbs)}")
    else:
        cc_tasks = [r for r in sched if r["type"] == "task" and r["chain"] == "critical"]
        if cc_tasks:
            last_cc = max(r["finish"] for r in cc_tasks)
            if pbs[0]["start"] != last_cc:
                errors.append(f"project buffer starts {pbs[0]['start']}, last critical task finishes {last_cc}")
        pb_links = parse_links(field(pbs[0], "predecessor_ids", "predecessors"))
        if len(pb_links) != 1 or pb_links[0][1] != "PB" or (
                pb_links[0][0] in rows
                and not (rows[pb_links[0][0]]["type"] == "task"
                         and rows[pb_links[0][0]]["chain"] == "critical")):
            errors.append(f"{pbs[0]['id']}: project buffer must have exactly one "
                          f"predecessor — the terminal critical-chain task via :PB "
                          f"(got {field(pbs[0], 'predecessor_ids', 'predecessors') or 'none'})")

    # 8. buffers consume no resources
    for r in sched:
        if r["type"] in BUFFER_LINK and field(r, "resource_ids", "resources").strip():
            errors.append(f"{r['id']}: buffer must not consume resources")

    # 10. buffers have positive length
    for r in sched:
        if r["type"] in BUFFER_LINK and r["duration"] < 1:
            errors.append(f"{r['id']}: zero-length buffer (duration {r['duration']}) "
                          f"protects nothing — omit it and flag the chain instead")

    # 11. every feeding buffer merges into exactly one protected successor
    fb_ids = {r["id"] for r in sched if r["type"] == "feeding_buffer"}
    merged = defaultdict(list)
    for tid, r in rows.items():
        for pid, ltype, lag in parse_links(field(r, "predecessor_ids", "predecessors")):
            if pid in fb_ids and ltype == "FB":
                merged[pid].append(tid)
    for fb in sorted(fb_ids):
        succs = merged.get(fb, [])
        if len(succs) != 1:
            errors.append(f"{fb}: feeding buffer must merge into exactly one successor "
                          f"via a :FB link (found {len(succs)}) — a buffer without a "
                          f"successor dangles outside the network")
            continue
        s = rows[succs[0]]
        if not (s["type"] == "task" and s["chain"] == "critical"):
            errors.append(f"{fb}: merge successor {succs[0]} must be a critical-chain task")

    # 12. no bypasses, no unbuffered merges into the critical chain
    fb_attach_of = {}  # attach task id -> (fb id, fb finish)
    for r in sched:
        if r["type"] != "feeding_buffer":
            continue
        for pid, ltype, _ in parse_links(field(r, "predecessor_ids", "predecessors")):
            if ltype == "FB":
                fb_attach_of[pid] = (r["id"], r["finish"])
    for tid, r in rows.items():
        if r["type"] != "task" or r["chain"] != "critical":
            continue
        for pid, ltype, lag in parse_links(field(r, "predecessor_ids", "predecessors")):
            p = rows.get(pid)
            if not p or p["type"] != "task" or p["chain"] == "critical":
                continue
            # a non-critical task feeds this critical task directly
            if pid in fb_attach_of and fb_attach_of[pid][1] == r["start"]:
                errors.append(f"{tid}: direct link from {pid} BYPASSES feeding buffer "
                              f"{fb_attach_of[pid][0]} — reroute the edge through the buffer")
            elif r["start"] - p["finish"] >= 1:
                errors.append(f"{tid}: unbuffered merge — non-critical {pid} feeds the "
                              f"critical chain directly with room for a feeding buffer")

    # 6. feeding buffer positioning: starts at its attach task's finish,
    # ends exactly on a critical-chain task's start
    cc_starts = {r["start"] for r in sched if r["type"] == "task" and r["chain"] == "critical"}
    for fb in (r for r in sched if r["type"] == "feeding_buffer"):
        own = parse_links(field(fb, "predecessor_ids", "predecessors"))
        fb_attach = [pid for pid, lt, _ in own if lt == "FB"]
        if len(own) != 1 or len(fb_attach) != 1:
            errors.append(f"{fb['id']}: feeding buffer must attach to exactly one "
                          f"task via :FB (got {field(fb, 'predecessor_ids', 'predecessors') or 'none'})")
        elif fb_attach[0] in rows and rows[fb_attach[0]]["finish"] != fb["start"]:
            errors.append(f"{fb['id']}: starts {fb['start']} but its attach task "
                          f"{fb_attach[0]} finishes {rows[fb_attach[0]]['finish']}")
        if fb["finish"] not in cc_starts:
            errors.append(
                f"{fb['id']}: end {fb['finish']} not anchored to a critical-chain "
                f"task start (its protected successor)")

    if errors:
        print(f"INVALID — {len(errors)} violation(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("VALID — all checks passed.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:5]))
