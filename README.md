# ccpm-scheduler

Deterministic Critical Chain Project Management (CCPM) scheduling as a Python
library and CLI — for humans, for AI agents, and for embedding in other tools.

Give it a project network (tasks, dependencies, duration estimates, resource
assignments) plus resource availability, and it produces a proper Critical
Chain schedule: resource-leveled, scheduled as late as possible, protected by
a project buffer and feeding buffers, with a buffer-aware Gantt chart.

Same input always yields byte-identical output — the scheduler is fully
deterministic, so it is scriptable, diffable, and testable.

## Status

Phases 1–2 complete: extracted behavior-preserving from the
[ccpm-scheduler Claude skill](https://github.com/rnwolf/ccpm-single-project-skill)
(guarded by byte-identical golden tests), with a typed model, library API,
and the `ccpm-scheduler` CLI. Coming next (see [PLAN.md](PLAN.md)): the
Claude skill drives this CLI (Phase 3), and the
[our-planner](https://github.com/rnwolf/our-planner) GUI imports the library
(Phase 4).

## CLI

Built for humans *and* AI agents: exit codes are a contract (0 = ok,
1 = problems found with the report still emitted, 2 = usage error), `--json`
prints a machine-readable document, there are no interactive prompts, and the
same input always produces byte-identical output.

```bash
ccpm-scheduler validate tasks.csv resources.csv calendar.csv
ccpm-scheduler build tasks.csv resources.csv --calendar calendar.csv \
    --out-dir plan --title "Website relaunch" --buffer-method cap
ccpm-scheduler check plan/schedule.csv tasks.csv resources.csv calendar.csv
ccpm-scheduler plot plan/schedule.csv plan/gantt.png --resources resources.csv
ccpm-scheduler graph plan/schedule.csv plan/project-network.html \
    --tasks tasks.csv --title "Website relaunch"   # interactive dependency graph
ccpm-scheduler schema network     # JSON Schema of the input format
```

`graph` writes a standalone interactive network view of the schedule
(vis-network from a CDN, data embedded — no build step or server): open the
HTML in any browser to zoom, pan, drag nodes, toggle hierarchical/free
layout, and click a node to inspect its schedule, resources, and links. The
Gantt shows *when*; the graph shows *why* — colors match the Gantt
(critical chain firebrick, feeding chains colored, buffers gold/khaki with
dashed attachment edges). A **resource filter** (All resources / Unassigned /
each named resource) fades everything except the selected resource's tasks,
so each team member can see their part in the context of the whole plan.
Task nodes show the realistic estimate next to the scheduled (optimal)
duration — the optimal/realistic balance is exactly what teams debate in
front of this view. (`--tasks tasks.csv` supplies the estimates for
schedules produced before v0.7; newer `schedule.csv` files carry them.)

The network input is either CSV files or a single JSON document (a path, or
`-` for stdin) in the exchange format:

```bash
echo '{"tasks": [...], "resources": [...]}' | ccpm-scheduler build - --json
```

`build` sizes buffers per `--buffer-method`: `cap` (Cut & Paste — the
default), `hchain` (50% of chain, the pre-0.9 behavior), or `rsem`
(root-squared error); a JSON input may carry its own `buffer_method` key,
which the flag overrides. Formulas, trade-offs, and mixed-estimate handling:
[docs/buffer-sizing.md](docs/buffer-sizing.md).

`build` validates first: on a broken network you get the same coded issue
report as `validate` (exit 1) and no files. `--json` reports carry stable
machine-readable issue codes (`E_CYCLE`, `E_NO_RESOURCE`,
`E_FRACTIONAL_ALLOCATION`, …) plus the offending task/resource ids;
`ccpm-scheduler schema report` describes the shape.

## Library API

```python
from ccpm_scheduler import (load_network, validate_network,
                            build_schedule, check_schedule, plot_schedule)

network = load_network("tasks.csv", "resources.csv", "calendar.csv")
report = validate_network(network)   # ValidationReport with coded Issues
if report.ok:
    result = build_schedule(network, title="My project")
    assert check_schedule(result.schedule, network).ok
    plot_schedule(result.schedule, "gantt.png",
                  resources=network.resources, calendar=network.calendar)
    print(result.stats.status_line("My project"))
```

Validation issues carry machine-readable codes (`E_CYCLE`, `E_NO_RESOURCE`,
`E_FRACTIONAL_ALLOCATION`, …) plus the offending task/resource ids, so an
embedding tool can annotate its own UI. Networks also load from a JSON
exchange format (`network_from_json` / `network_to_json`) that accepts
structured predecessor links (`{"id": 2, "type": "SS", "lag": 2}`), numeric
ids, and per-resource allocation maps — the shape GUI tools naturally emit.
Fractional allocations and capacities are rejected with precise errors in v1
(whole resources only).

(`python -m ccpm_scheduler` is equivalent to the `ccpm-scheduler` command;
the individual stages also remain runnable as `python -m
ccpm_scheduler.validate` etc. with their original argument conventions.)

## Input contract

**tasks.csv** — `id, name, realistic_duration, optimal_duration (optional),
predecessor_ids, resource_ids, url (optional)`

- `realistic_duration`: estimate with safety included; `optimal_duration`:
  padding-free estimate. If `optimal_duration` is missing, the classic 50% cut
  is applied. (Legacy names `duration_safe`/`duration_aggressive` are accepted.)
- `predecessor_ids`: semicolon-separated links — bare id = Finish-to-Start,
  typed links with lag supported: `A:SS+2`, `A:FF`, `A:SF`. Buffer rows in the
  *output* use the CCPM-specific `:PB`/`:FB` link types.
- `resource_ids`: semicolon-separated; every task needs at least one resource.

**resources.csv** — `id, name, capacity, url (optional)`; capacity defaults to 1.

**calendar.csv** (optional) — `resource_id, from, to, capacity`: overrides a
resource's capacity on the half-open day range `[from, to)`; `capacity = 0`
means unavailable. Tasks execute contiguously — they never pause across an
outage.

Durations are working days; the schedule uses integer day offsets from day 0.

## Output

- `schedule.csv` — tasks and buffers with start/finish, chain membership
  (`critical`, `feeding-n`), link notation (buffers attached via `:PB`/`:FB`),
  and each task's `realistic_duration` alongside its scheduled (optimal)
  `duration` — filter by chain to audit how much safety left the tasks
  versus what landed in the chain's buffer
- `summary.md` — critical chain, project duration, buffer sizes, promised
  completion date (= end of the project buffer), the buffer-sizing method
  used, and how many tasks in each protected chain had derived
  (single-point) safety estimates. The methods (CAP / HCHAIN / RSEM), their
  trade-offs, and how mixed single-/two-point estimates are handled are
  documented in [docs/buffer-sizing.md](docs/buffer-sizing.md)
- `gantt.png` — critical chain, feeding chains, buffers, dependency arrows,
  and a resource-utilization panel on the same time axis
- `project-network.html` (via `graph`) — standalone interactive dependency
  graph of the same schedule, for exploring the network structure the
  Gantt can't show

## Development

```bash
uv sync
uv run pytest
```

The golden tests in `tests/` assert byte-identical `schedule.csv`/`summary.md`
for five reference projects. Regenerate goldens only for deliberate, reviewed
behavior changes.

## License

Dual-licensed under either of [MIT](LICENSE-MIT) or
[Apache License 2.0](LICENSE-APACHE), at your option.
