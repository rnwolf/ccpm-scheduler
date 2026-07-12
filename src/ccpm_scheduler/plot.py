"""Render a CCPM schedule as a buffer-aware Gantt chart PNG with
dependency-link arrows and a resource-utilization sub-chart on the same
time axis.

Library API:  plot_schedule(schedule, out_path, title=..., resources=...,
                            calendar=..., ...)
CLI:          python -m ccpm_scheduler.plot schedule.csv gantt.png
                  [--title "My project"] [--resources resources.csv]
                  [--calendar calendar.csv] [--no-utilization]
                  [--no-links] [--critical-label "Critical path"]

The Gantt legend is built from what the schedule actually contains (buffers,
feeding chains, unlabeled tasks), and the label for the critical bars can be
overridden with --critical-label — e.g. "Critical path" when rendering a
plain CPM schedule with the same script.

Dependency links are read from an optional `predecessor_ids` column in
schedule.csv (legacy name `predecessors` also accepted). Link notation:
`A` (Finish-to-Start, the default), `A:SS`, `A:FF`, `A:SF`, with optional
lag, e.g. `A:SS+2`. Multiple links are separated by `;`. Arrows are drawn
for every link; non-FS links carry a small SS/FF/SF label since readers
assume FS by default.

Buffer attachments use the CCPM-specific types `:PB` (project buffer) and
`:FB` (feeding buffer). They are drawn dashed, because a buffer is not work
driven by its predecessor: during execution the buffer's END stays anchored
(to the commitment date for PB, to the protected critical-chain task for FB)
and predecessor slippage consumes the buffer from the left instead of pushing
it. Buffer bars get a "<id> <n>d" label and the project buffer ends in a
commitment-date diamond.

The utilization panel shows, per resource per day, how much capacity is used.
Within capacity = steelblue; over capacity = red (a red block means the
leveling step failed). Pass --resources to use real capacities; default is 1.
Pass --calendar for day-range capacity overrides (`resource_id, from, to,
capacity`, half-open [from, to)): days with capacity 0 are drawn as grey
hatched "unavailable" blocks, and overload detection uses the effective
per-day capacity.

Color code (Gantt): critical chain = firebrick with cross-hatch (so it stays
distinguishable from other red-ish bars and in greyscale prints), feeding
chains = colored, buffers = gold/khaki with diagonal hatching, other tasks
= grey.
"""
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from . import io
from .model import Schedule, as_int

split_ids = io.split_tokens


def field(row, *names):
    """First present value among column names (new name first, legacy after)."""
    for n in names:
        if row.get(n) is not None:
            return row[n]
    return ""


def parse_links(s):
    """'A;B:SS+2' -> [('A','FS',0), ('B','SS',2)]"""
    return [(l.pred_id, l.type, l.lag)
            for l in io.parse_links(s, buffer_links=True)]


def plot_schedule(schedule: Schedule, out_path, title="CCPM Schedule",
                  resources=None, calendar=None,
                  show_util=True, show_links=True,
                  critical_label="Critical chain"):
    """Render the schedule to a PNG. resources is an optional list of
    Resource (for real capacities; default 1); calendar an optional list of
    CalendarWindow for per-day overrides."""
    rows = [r.to_csv_dict() for r in schedule.rows]

    capacity = {}
    for rr in resources or []:
        capacity[rr.id] = as_int(rr.capacity)

    overrides = defaultdict(list)  # resource -> [(from, to, capacity)]
    for w in calendar or []:
        overrides[w.resource_id].append(
            (as_int(w.start), as_int(w.end), as_int(w.capacity)))

    def cap_on(res, day):
        for lo, hi, cap in overrides.get(res, ()):
            if lo <= day < hi:
                return cap
        return capacity.get(res, 1)

    # daily demand per resource (tasks only - buffers consume no resources)
    demand = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["type"] != "task":
            continue
        for res in split_ids(field(r, "resource_ids", "resources")):
            for day in range(r["start"], r["finish"]):
                demand[res][day] += 1
    resources = sorted(set(demand) | set(capacity) | set(overrides))
    show_util = show_util and bool(resources)

    rows.sort(key=lambda r: (r["start"], r["finish"], r["id"]))
    feeding_chains = sorted({r["chain"] for r in rows if r["chain"].startswith("feeding")})
    feed_cmap = matplotlib.colormaps["tab10"]
    # tab10 indices, skipping 3 (red - reserved for the critical chain family)
    feed_palette = [2, 0, 4, 5, 6, 8, 9, 1]
    feed_color = {c: feed_cmap(feed_palette[i % len(feed_palette)])
                  for i, c in enumerate(feeding_chains)}

    t_end = max(r["finish"] for r in rows)
    n_res = len(resources)
    if show_util:
        fig, (ax, axu) = plt.subplots(
            2, 1, sharex=True,
            figsize=(11, 0.5 * len(rows) + 0.45 * n_res + 3),
            gridspec_kw={"height_ratios": [len(rows), max(n_res, 2)],
                         "hspace": 0.12})
    else:
        fig, ax = plt.subplots(figsize=(11, 0.5 * len(rows) + 2))
        axu = None

    # ---------------- Gantt panel ----------------
    ypos = {}
    yticks, ylabels = [], []
    for i, r in enumerate(rows):
        y = len(rows) - i
        ypos[r["id"]] = y
        dur = r["finish"] - r["start"]
        if r["type"] == "project_buffer":
            color, hatch = "gold", "//"
        elif r["type"] == "feeding_buffer":
            color, hatch = "khaki", "//"
        elif r["chain"] == "critical":
            color, hatch = "firebrick", "xx"
        elif r["chain"] in feed_color:
            color, hatch = feed_color[r["chain"]], None
        else:
            color, hatch = "grey", None
        ax.barh(y, dur, left=r["start"], height=0.6, color=color,
                hatch=hatch, edgecolor="black", linewidth=0.5, zorder=2)
        if dur == 0:  # zero-duration milestone (e.g. the Finish milestone)
            ax.plot([r["start"]], [y], marker="D", color=color,
                    markeredgecolor="black", markersize=8, zorder=3)
        res = field(r, "resource_ids", "resources").replace(";", ",")
        if res:
            ax.text(r["finish"] + 0.2, y, res, va="center", fontsize=8,
                    color="dimgrey", zorder=3)
        if r["type"] in ("project_buffer", "feeding_buffer"):
            ax.text(r["start"] + dur / 2, y, f"{r['id']} {dur}d",
                    ha="center", va="center", fontsize=7.5, zorder=3)
            if r["type"] == "project_buffer":
                ax.plot([r["finish"]], [y], marker="D", color="black",
                        markersize=7, zorder=5)
                ax.text(r["finish"], y - 0.45, "commitment",
                        ha="right", va="top", fontsize=7, color="black", zorder=5)
        yticks.append(y)
        ylabels.append(f"{r['id']}  {r.get('name', '')}")

    # ---------------- dependency arrows ----------------
    if show_links:
        byid = {r["id"]: r for r in rows}
        for r in rows:
            for pid, ltype, lag in parse_links(field(r, "predecessor_ids", "predecessors")):
                p = byid.get(pid)
                if p is None:
                    continue
                # anchor x on each bar depends on link type
                x_from = p["finish"] if ltype in ("FS", "FF", "PB", "FB") else p["start"]
                x_to = r["start"] if ltype in ("FS", "SS", "PB", "FB") else r["finish"]
                y_from, y_to = ypos[pid], ypos[r["id"]]
                going_down = y_to < y_from
                # leave pred horizontally, arrive succ vertically at bar edge
                edge = 0.3 if going_down else -0.3
                if ltype in ("SS", "SF"):
                    y_from -= edge  # exit along the pred bar edge facing the successor
                buffer_link = ltype in ("PB", "FB")
                ax.annotate(
                    "", xy=(x_to, y_to + edge), xytext=(x_from, y_from),
                    arrowprops=dict(arrowstyle="->", color="0.25", lw=1.0,
                                    linestyle=(0, (3, 2)) if buffer_link else "solid",
                                    shrinkA=0, shrinkB=0,
                                    connectionstyle="angle,angleA=0,angleB=90,rad=2"),
                    zorder=4)
                if ltype != "FS" or lag:
                    lbl = ltype if ltype != "FS" else ""
                    if lag:
                        lbl += f"{lag:+d}"
                    ax.text(x_to + 0.15, (y_from + y_to + edge) / 2, lbl,
                            fontsize=6.5, color="0.25", va="center", zorder=4)

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=9)
    ax.set_title(title, loc="left")
    ax.grid(axis="x", linestyle=":", alpha=0.5)
    ax.set_xlim(0, t_end + 1)
    ax.set_ylim(0.3, len(rows) + 0.7)
    handles = []
    if any(r["chain"] == "critical" for r in rows):
        handles.append(Patch(facecolor="firebrick", hatch="xx", label=critical_label))
    if feeding_chains:
        handles.append(Patch(facecolor=feed_cmap(2), label="Feeding chain"))
    if any(r["type"] == "task" and r["chain"] == "none" for r in rows):
        handles.append(Patch(facecolor="grey", label="Other task"))
    if any(r["type"] == "project_buffer" for r in rows):
        handles.append(Patch(facecolor="gold", hatch="//", label="Project buffer"))
    if any(r["type"] == "feeding_buffer" for r in rows):
        handles.append(Patch(facecolor="khaki", hatch="//", label="Feeding buffer"))
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.02),
              ncol=len(handles), fontsize=8, frameon=False)

    # ---------------- Resource utilization panel ----------------
    if axu is not None:
        for j, res in enumerate(resources):
            y = n_res - j
            for day in range(t_end):
                cap = cap_on(res, day)
                d = demand[res].get(day, 0)
                if cap == 0:
                    axu.barh(y, 1, left=day, height=0.7, color="0.85",
                             hatch="///", edgecolor="white", linewidth=0.3)
                if d == 0:
                    continue
                over = d > cap
                axu.barh(y, 1, left=day, height=0.7,
                         color="red" if over else "steelblue",
                         alpha=min(1.0, 0.45 + 0.55 * d / max(cap, 1)),
                         edgecolor="white", linewidth=0.3)
                if cap > 1 or over:
                    axu.text(day + 0.5, y, str(d), ha="center", va="center",
                             fontsize=6, color="white")
        axu.set_yticks([n_res - j for j in range(n_res)])
        axu.set_yticklabels(
            [f"{r} (cap {capacity.get(r, 1)})" for r in resources], fontsize=9)
        axu.set_ylim(0.4, n_res + 0.6)
        axu.set_title("Resource utilization", fontsize=10, loc="left")
        util_handles = [
            Patch(facecolor="steelblue", label="Within capacity"),
            Patch(facecolor="red", label="Overloaded (over capacity)"),
        ]
        if overrides:
            util_handles.append(
                Patch(facecolor="0.85", hatch="///", label="Unavailable"))
        axu.legend(handles=util_handles, loc="lower right",
                   bbox_to_anchor=(1.0, 1.0), ncol=len(util_handles),
                   fontsize=8, frameon=False)
        axu.grid(axis="x", linestyle=":", alpha=0.5)
        axu.set_xlabel("Working day")
    else:
        ax.set_xlabel("Working day")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main(schedule_path, out_path, title="CCPM Schedule",
         resources_path=None, calendar_path=None,
         show_util=True, show_links=True, critical_label="Critical chain"):
    plot_schedule(
        io.load_schedule(schedule_path), out_path, title=title,
        resources=io.load_resources(resources_path) if resources_path else None,
        calendar=io.load_calendar(calendar_path) if calendar_path else None,
        show_util=show_util, show_links=show_links,
        critical_label=critical_label)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    argv = sys.argv
    if len(argv) < 3:
        print(__doc__)
        sys.exit(2)
    title, resources_path, calendar_path = "CCPM Schedule", None, None
    show_util, show_links, critical_label = True, True, "Critical chain"
    if "--title" in argv:
        i = argv.index("--title"); title = argv[i + 1]; del argv[i:i + 2]
    if "--resources" in argv:
        i = argv.index("--resources"); resources_path = argv[i + 1]; del argv[i:i + 2]
    if "--calendar" in argv:
        i = argv.index("--calendar"); calendar_path = argv[i + 1]; del argv[i:i + 2]
    if "--critical-label" in argv:
        i = argv.index("--critical-label"); critical_label = argv[i + 1]; del argv[i:i + 2]
    if "--no-utilization" in argv:
        argv.remove("--no-utilization"); show_util = False
    if "--no-links" in argv:
        argv.remove("--no-links"); show_links = False
    main(argv[1], argv[2], title, resources_path, calendar_path,
         show_util, show_links, critical_label)
