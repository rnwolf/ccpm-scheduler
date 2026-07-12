"""Build a CCPM schedule — the deterministic reference implementation.
The same input always produces the same schedule.

Library API:  build_schedule(network, title=...) -> BuildResult
CLI:          python -m ccpm_scheduler.build tasks.csv resources.csv
                  [--calendar calendar.csv] [--out-dir DIR] [--title "My project"]

The CLI writes DIR/schedule.csv and DIR/summary.md (DIR defaults to the
current directory). Validate the network first (ccpm_scheduler.validate) —
this builder assumes a logically valid network (acyclic, known ids, positive
durations, every task resourced) and reports input problems only crudely.

Steps: normalize (optimal durations = ceil(realistic/2) unless given) ->
ALAP baseline (calendar-aware) -> resource leveling (earlier-only; if
infeasible under deadline T, retry with T+1) -> critical chain (resource
links + calendar-gap continuation) -> feeding chains -> buffers (50% rule;
a feeding buffer bridges the gap to its anchor; feeding-chain shifts drag
non-critical external predecessors; zero-length buffers are omitted and the
chain flagged) -> merges: EVERY edge from non-critical work into the
critical chain gets its own feeding buffer, the protected successor lists
the buffer as `<FBid>:FB`, and the direct feeder->join link is rerouted
through the buffer (a plain edge kept alongside would bypass it). Feeding
chains that run to the project end merge into a zero-duration FINISH
milestone on the critical chain, and the project buffer attaches to that
milestone alone -> schedule.csv + summary.md.

Verify the output with ccpm_scheduler.check and render it with
ccpm_scheduler.plot.
"""
import math, sys
from collections import defaultdict

from . import io
from .model import (Network, CcpmError, Schedule, ScheduleRow,
                    BuildResult, BuildStats, as_int)

LINK_RE = io.INPUT_LINK_RE


class Net:
    """The engine's working view of a Network."""
    def __init__(self, network: Network):
        self.T = {}     # tid -> dict(name, dur, links, res, url, predstr)
        for t in network.tasks:
            try:
                dur = t.duration
            except ValueError as e:
                raise CcpmError(str(e)) from None
            self.T[t.id] = dict(
                name=t.name, dur=dur,
                links=[(l.pred_id, l.type, l.lag) for l in t.links],
                predstr=t.predecessor_notation(),
                res=list(t.resource_ids),
                url=t.url or "")
        try:
            self.caps = {r.id: as_int(r.capacity, f"resource {r.id}: capacity")
                         for r in network.resources}
            self.cal = defaultdict(list)
            for w in network.calendar:
                self.cal[w.resource_id].append(
                    (as_int(w.start, "calendar from"),
                     as_int(w.end, "calendar to"),
                     as_int(w.capacity, "calendar capacity")))
        except ValueError as e:
            raise CcpmError(str(e)) from None
        self.has_calendar = network.has_calendar
        self.succ = defaultdict(list)   # tid -> [(sid, type, lag)]
        for tid, t in self.T.items():
            for pid, lt, lag in t["links"]:
                if pid not in self.T:
                    raise CcpmError(f"task {tid}: unknown predecessor {pid}")
                self.succ[pid].append((tid, lt, lag))
        for res in {r for t in self.T.values() for r in t["res"]}:
            if res not in self.caps:
                raise CcpmError(f"unknown resource {res}")
        # longest precedence path through each task (optimal durations)
        self.path_through = {}
        down, up = {}, {}
        def longest_down(tid):
            if tid not in down:
                down[tid] = self.T[tid]["dur"] + max(
                    (longest_down(s) for s, _, _ in self.succ[tid]), default=0)
            return down[tid]
        def longest_up(tid):
            if tid not in up:
                up[tid] = self.T[tid]["dur"] + max(
                    (longest_up(p) for p, _, _ in self.T[tid]["links"]), default=0)
            return up[tid]
        for tid in self.T:
            self.path_through[tid] = (longest_up(tid) + longest_down(tid)
                                      - self.T[tid]["dur"])

    def cap_on(self, res, day):
        for lo, hi, cap in self.cal.get(res, ()):
            if lo <= day < hi:
                return cap
        return self.caps.get(res, 1)

    def cal_ok(self, tid, start):
        """Calendar walls only: every day of the span has capacity >= 1."""
        if start < 0:
            return False
        return all(self.cap_on(r, d) >= 1
                   for r in self.T[tid]["res"]
                   for d in range(start, start + self.T[tid]["dur"]))


def try_schedule(net, T):
    """ALAP + leveling under deadline T. Returns start map or None."""
    ids = list(net.T)
    dur = {i: net.T[i]["dur"] for i in ids}

    # forward ASAP (sanity only, ensures T is not below critical length)
    es = {i: 0 for i in ids}
    for _ in range(len(ids) + 2):
        changed = False
        for i in ids:
            lo = 0
            for p, lt, lag in net.T[i]["links"]:
                pa = es[p] + (dur[p] if lt in ("FS", "FF") else 0) + lag
                lo = max(lo, pa - (dur[i] if lt in ("FF", "SF") else 0))
            while not net.cal_ok(i, lo):
                lo += 1
            if lo > es[i]:
                es[i], changed = lo, True
        if not changed:
            break
    if max(es[i] + dur[i] for i in ids) > T:
        return None

    # backward ALAP under T (calendar-aware)
    ls = {i: T - dur[i] for i in ids}
    for _ in range(len(ids) + 2):
        changed = False
        for i in ids:
            hi = T - dur[i]
            for s, lt, lag in net.succ[i]:
                if lt == "FS":
                    hi = min(hi, ls[s] - lag - dur[i])
                elif lt == "SS":
                    hi = min(hi, ls[s] - lag)
                elif lt == "FF":
                    hi = min(hi, ls[s] + dur[s] - lag - dur[i])
                elif lt == "SF":
                    hi = min(hi, ls[s] + dur[s] - lag)
            while hi >= 0 and not net.cal_ok(i, hi):
                hi -= 1
            if hi < 0:
                return None
            if hi < ls[i]:
                ls[i], changed = hi, True
        if not changed:
            break

    start = dict(ls)

    def drag_preds(tid):
        """Shift predecessors earlier minimally to satisfy links."""
        for p, lt, lag in net.T[tid]["links"]:
            if lt == "FS":
                bound = start[tid] - lag - dur[p]
            elif lt == "SS":
                bound = start[tid] - lag
            elif lt == "FF":
                bound = start[tid] + dur[tid] - lag - dur[p]
            else:  # SF
                bound = start[tid] + dur[tid] - lag
            if start[p] > bound:
                while bound >= 0 and not net.cal_ok(p, bound):
                    bound -= 1
                if bound < 0:
                    return False
                start[p] = bound
                if not drag_preds(p):
                    return False
        return True

    for _ in range(500):
        demand = defaultdict(lambda: defaultdict(int))
        for i in ids:
            for r in net.T[i]["res"]:
                for d in range(start[i], start[i] + dur[i]):
                    demand[r][d] += 1
        overload = [(d, r) for r in demand for d in demand[r]
                    if demand[r][d] > net.cap_on(r, d)]
        if not overload:
            return start
        day, res = max(overload, key=lambda x: (x[0], [-ord(c) for c in x[1]]))
        active = sorted(i for i in ids if res in net.T[i]["res"]
                        and start[i] <= day < start[i] + dur[i])
        ranked = sorted(active, key=lambda i: (-net.path_through[i],
                                               -(start[i] + dur[i]), i))
        keeper, mover = ranked[0], ranked[-1]
        s = start[keeper] - dur[mover]
        while s >= 0 and not net.cal_ok(mover, s):
            s -= 1
        if s < 0:
            return None
        start[mover] = s
        if not drag_preds(mover):
            return None
    return None


def build_schedule(network: Network, title="CCPM schedule") -> BuildResult:
    """Build the CCPM schedule for a (validated) network.

    Returns the schedule rows, the summary markdown, and build statistics.
    Raises CcpmError when the network is unschedulable or malformed.
    """
    net = Net(network)
    ids = list(net.T)
    dur = {i: net.T[i]["dur"] for i in ids}
    T0 = 0
    start = None
    for T in range(sum(dur.values()) + 1):
        start = try_schedule(net, T)
        if start is not None:
            T0 = T
            break
    if start is None:
        raise CcpmError("no feasible schedule found (check the calendar leaves "
                        "room for every task)")
    fin = {i: start[i] + dur[i] for i in ids}

    # ---- critical chain ----
    def is_pred(x, cur):
        return any(p == x for p, _, _ in net.T[cur]["links"])

    def shares(x, cur):
        return bool(set(net.T[x]["res"]) & set(net.T[cur]["res"]))

    def candidates(cur, exclude):
        out = []
        for x in ids:
            if x in exclude or not (is_pred(x, cur) or shares(x, cur)):
                continue
            if fin[x] == start[cur]:
                out.append(x)
            elif fin[x] < start[cur] and all(
                    not net.cal_ok(cur, s)
                    for s in range(fin[x], start[cur])):
                out.append(x)  # calendar outage, not slack, bounds cur
        return out

    reach_memo = {}
    def reach(x, exclude):
        key = x
        if key in reach_memo:
            return reach_memo[key]
        cands = candidates(x, exclude | {x})
        r = start[x] if not cands else min(
            reach(c, exclude | {x}) for c in cands)
        reach_memo[key] = r
        return r

    last = max(ids, key=lambda i: (fin[i], [-ord(c) for c in i]))
    cc, cur = [last], last
    while True:
        cands = candidates(cur, set(cc))
        if not cands:
            break
        nxt = min(cands, key=lambda x: (reach(x, set(cc)),
                                        0 if is_pred(x, cur) else 1, x))
        cc.append(nxt)
        cur = nxt
    cc.reverse()
    cc_set = set(cc)

    # ---- feeding chains ----
    noncc = [i for i in ids if i not in cc_set]
    tails = []
    for t in noncc:
        succs = [s for s, _, _ in net.succ[t]]
        cc_succ = [s for s in succs if s in cc_set]
        noncc_succ = [s for s in succs if s not in cc_set]
        if cc_succ:
            tails.append((t, min(cc_succ, key=lambda s: start[s])))
        elif not noncc_succ:
            tails.append((t, None))  # sink -> protected by PB anchor
    back = {}
    def back_len(t):
        if t not in back:
            back[t] = dur[t] + max((back_len(p) for p, _, _ in net.T[t]["links"]
                                    if p not in cc_set), default=0)
        return back[t]
    tails.sort(key=lambda x: (-back_len(x[0]), x[0]))
    assigned, chains = set(), []
    for tail, join in tails:
        if tail in assigned:
            continue
        chain, cur = [tail], tail
        assigned.add(tail)
        while True:
            preds = [p for p, _, _ in net.T[cur]["links"]
                     if p not in cc_set and p not in assigned]
            if not preds:
                break
            cur = max(preds, key=lambda p: (back_len(p), p))
            chain.append(cur)
            assigned.add(cur)
        chains.append(dict(tasks=list(reversed(chain)), tail=tail, join=join))

    # ---- buffers ----
    last_cc_fin = max(fin[i] for i in cc)
    pb_size = math.ceil(0.5 * sum(dur[i] for i in cc))
    for ch in chains:
        ch["anchor"] = start[ch["join"]] if ch["join"] else last_cc_fin
    chains.sort(key=lambda c: (c["anchor"], c["tail"]))

    # topological order between chains (a chain feeding another shifts first)
    def chain_deps(a, b):  # True if a has a member that is a pred of a member of b
        bt = set(b["tasks"])
        return any(s in bt for m in a["tasks"] for s, _, _ in net.succ[m])
    ordered = []
    remaining = chains[:]
    while remaining:
        for c in remaining:
            if not any(chain_deps(o, c) for o in remaining if o is not c):
                ordered.append(c); remaining.remove(c); break
        else:
            ordered.extend(remaining); break

    def try_shift(members, d):
        """Shift chain members d days earlier, dragging non-critical external
        predecessors along (leveling semantics). Returns the full map of new
        starts, or None if blocked by a CC task, the calendar, day 0, or
        resource capacity."""
        new = {m: start[m] - d for m in members}
        queue = list(members)
        while queue:
            t = queue.pop()
            t_start = new.get(t, start[t])
            t_fin = t_start + dur[t]
            for p, lt, lag in net.T[t]["links"]:
                if lt == "FS":
                    bound = t_start - lag - dur[p]
                elif lt == "SS":
                    bound = t_start - lag
                elif lt == "FF":
                    bound = t_fin - lag - dur[p]
                else:  # SF
                    bound = t_fin - lag
                if new.get(p, start[p]) > bound:
                    if p in cc_set:
                        return None  # critical chain tasks never move
                    while bound >= 0 and not net.cal_ok(p, bound):
                        bound -= 1
                    if bound < 0:
                        return None
                    new[p] = bound
                    queue.append(p)
        for m, s in new.items():
            if not net.cal_ok(m, s):
                return None
        demand = defaultdict(lambda: defaultdict(int))
        for i in ids:
            s = new.get(i, start[i])
            for r in net.T[i]["res"]:
                for dd in range(s, s + dur[i]):
                    demand[r][dd] += 1
        for r in demand:
            for dd, n in demand[r].items():
                if n > net.cap_on(r, dd):
                    return None
        return new

    for ch in ordered:
        members = ch["tasks"]
        size = math.ceil(0.5 * sum(dur[i] for i in members))
        ch["size"] = size
        chain_fin = max(fin[i] for i in members)
        want = chain_fin - (ch["anchor"] - size)
        if want <= 0:
            continue
        for d in range(want, 0, -1):
            new = try_shift(members, d)
            if new is not None:
                for m, s in new.items():
                    start[m] = s
                    fin[m] = s + dur[m]
                break

    assert min(start.values()) >= 0

    # ---- chain labels ----
    chain_label = {}
    for n, ch in enumerate(sorted(chains, key=lambda c: (c["anchor"], c["tail"])), 1):
        ch["n"] = n
        for m in ch["tasks"]:
            chain_label[m] = f"feeding-{n}"

    # ---- merge points: EVERY edge from non-critical work into the critical
    # chain (or to the project end) is a merge and gets its own feeding
    # buffer. Chain-tail merges are sized on the chain; extra edges (a task
    # that also feeds the chain elsewhere, like a shared prefix) are sized
    # on the feeder's backward non-critical closure. ----
    def back_closure(x):
        seen, stack = {x}, [x]
        while stack:
            t = stack.pop()
            for p, _, _ in net.T[t]["links"]:
                if p not in cc_set and p not in seen:
                    seen.add(p)
                    stack.append(p)
        return seen

    merges = [dict(attach=ch["tasks"][-1], join=ch["join"], size=ch["size"],
                   tasks=ch["tasks"]) for ch in chains]
    covered = {(m["attach"], m["join"]) for m in merges}
    for x in sorted(noncc):
        for j in sorted({s for s, _, _ in net.succ[x] if s in cc_set}):
            if (x, j) in covered:
                continue
            closure = sorted(back_closure(x))
            size = math.ceil(0.5 * sum(dur[i] for i in closure))
            want = fin[x] - (start[j] - size)
            for d in range(max(want, 0), 0, -1):
                new = try_shift(closure, d)
                if new is not None:
                    for m, s in new.items():
                        start[m] = s
                        fin[m] = s + dur[m]
                    break
            merges.append(dict(attach=x, join=j, size=size, tasks=closure))

    for mg in merges:
        mg["anchor"] = start[mg["join"]] if mg["join"] else last_cc_fin
    buffered = [mg for mg in sorted(merges, key=lambda m: (m["anchor"], m["attach"]))
                if mg["anchor"] - fin[mg["attach"]] >= 1]
    # No room for a buffer: never emit a zero-length one - flag the merge.
    unprotected = [mg for mg in merges if mg not in buffered]

    finish_needed = any(mg["join"] is None for mg in buffered)
    merge_links, reroute = defaultdict(list), defaultdict(set)
    for m, mg in enumerate(buffered, 1):
        mg["id"] = f"FB{m}"
        succ = mg["join"] if mg["join"] else "FINISH"
        merge_links[succ].append(f"FB{m}:FB")
        if mg["join"]:
            # the buffer REPLACES the direct feeder->join link: a plain edge
            # kept alongside it would bypass the buffer (feeder slippage
            # would push the join task instead of consuming buffer)
            reroute[mg["join"]].add(mg["attach"])

    # ---- emit schedule.csv ----
    def out_preds(tid, base):
        toks = [t for t in (base or "").replace(";", " ").replace(",", " ").split()
                if not (LINK_RE.match(t) and LINK_RE.match(t).group("id") in reroute.get(tid, ()))]
        return ";".join(toks + merge_links.get(tid, []))

    rows = []
    for i in sorted(ids, key=lambda i: (start[i], fin[i], i)):
        rows.append(dict(id=i, name=net.T[i]["name"], type="task",
                         chain="critical" if i in cc_set else chain_label.get(i, "none"),
                         start=start[i], finish=fin[i], duration=dur[i],
                         resource_ids=";".join(net.T[i]["res"]),
                         predecessor_ids=out_preds(i, net.T[i]["predstr"]),
                         url=net.T[i]["url"]))
    for mg in buffered:
        f0 = fin[mg["attach"]]
        rows.append(dict(id=mg["id"], name=f"Feeding buffer {mg['id'][2:]}",
                         type="feeding_buffer",
                         chain=chain_label.get(mg["attach"], "none"),
                         start=f0, finish=mg["anchor"], duration=mg["anchor"] - f0,
                         resource_ids="", predecessor_ids=f"{mg['attach']}:FB", url=""))
    last_cc = max(cc, key=lambda i: fin[i])
    if finish_needed:
        # zero-duration milestone on the critical chain: end-running feeding
        # buffers merge here, and the project buffer hangs off it alone
        rows.append(dict(id="FINISH", name="Finish", type="task",
                         chain="critical", start=last_cc_fin, finish=last_cc_fin,
                         duration=0, resource_ids="",
                         predecessor_ids=out_preds("FINISH", last_cc), url=""))
        pb_pred = "FINISH:PB"
    else:
        pb_pred = f"{last_cc}:PB"
    rows.append(dict(id="PB", name="Project buffer", type="project_buffer",
                     chain="critical", start=last_cc_fin,
                     finish=last_cc_fin + pb_size, duration=pb_size,
                     resource_ids="", predecessor_ids=pb_pred, url=""))
    schedule = Schedule(rows=[ScheduleRow(**r) for r in rows])

    # ---- summary.md ----
    def link(i):
        n = f"{i} {net.T[i]['name']}"
        return f"[{n}]({net.T[i]['url']})" if net.T[i]["url"] else n
    promise = last_cc_fin + pb_size
    L = [f"# {title} — CCPM schedule", "",
         f"- **Critical chain**: {' → '.join(link(i) for i in cc)}",
         f"- **Critical chain length**: {sum(dur[i] for i in cc)} working days"
         f" (work finishes day {last_cc_fin})",
         f"- **Project buffer**: {pb_size} days → **promised completion: day {promise}**", ""]
    if buffered:
        L.append("| Feeding buffer | Protects | Size (days) | Merges into |")
        L.append("|---|---|---|---|")
        for mg in buffered:
            f0 = fin[mg["attach"]]
            anchor = link(mg["join"]) if mg["join"] else "the Finish milestone"
            L.append(f"| {mg['id']} | {' → '.join(link(m) for m in mg['tasks'])} "
                     f"| {mg['anchor'] - f0} | start of {anchor} |")
        L.append("")
    for mg in unprotected:
        where = link(mg["join"]) if mg["join"] else "the project end"
        L.append(f"**Warning**: the merge of {' → '.join(link(m) for m in mg['tasks'])} "
                 f"into {where} has no room for a feeding buffer — that path is "
                 f"effectively critical. Watch it as closely as the critical chain.")
        L.append("")
    if net.has_calendar:
        L.append("Resource availability from `calendar.csv` is honored: tasks are "
                 "placed contiguously around outage windows (grey blocks in the "
                 "Gantt utilization panel), never split across them.")
        L.append("")
    L.append("Durations are optimal (padding-free) estimates; overruns are expected roughly "
             "half the time and consume buffer — the promise date only moves if "
             "a buffer runs dry. Work the critical chain relay-runner style: "
             "hand off immediately, no multitasking.")

    stats = BuildStats(deadline=T0, critical_chain=list(cc),
                       critical_chain_length=sum(dur[i] for i in cc),
                       project_buffer=pb_size, promise_day=promise,
                       merges=len(merges), buffered=len(buffered),
                       unprotected=len(unprotected),
                       finish_milestone=finish_needed)
    return BuildResult(schedule=schedule, summary_markdown="\n".join(L) + "\n",
                       title=title, stats=stats)


def main(tasks_path, resources_path, calendar_path, out_dir, title):
    try:
        network = io.load_network(tasks_path, resources_path, calendar_path)
        result = build_schedule(network, title)
    except CcpmError as e:
        print(f"error: {e} — run the validator (ccpm_scheduler.validate) "
              f"for a full report", file=sys.stderr)
        sys.exit(1)
    io.write_build_outputs(result, out_dir)
    print(result.stats.status_line(result.title))


if __name__ == "__main__":
    argv = sys.argv
    calendar_path, out_dir, title = None, ".", "CCPM schedule"
    if "--calendar" in argv:
        i = argv.index("--calendar"); calendar_path = argv[i + 1]; del argv[i:i + 2]
    if "--out-dir" in argv:
        i = argv.index("--out-dir"); out_dir = argv[i + 1]; del argv[i:i + 2]
    if "--title" in argv:
        i = argv.index("--title"); title = argv[i + 1]; del argv[i:i + 2]
    if len(argv) != 3:
        print(__doc__)
        sys.exit(2)
    main(argv[1], argv[2], calendar_path, out_dir, title)
