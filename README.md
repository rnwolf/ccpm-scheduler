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

Phase 1 (extraction): the four pipeline stages live as importable, runnable
modules, extracted behavior-preserving from the
[ccpm-scheduler Claude skill](https://github.com/rnwolf/ccpm-single-project-skill)
and guarded by byte-identical golden tests.

```bash
python -m ccpm_scheduler.validate tasks.csv resources.csv [calendar.csv]
python -m ccpm_scheduler.build tasks.csv resources.csv [--calendar calendar.csv] \
    [--out-dir DIR] [--title "My project"]
python -m ccpm_scheduler.check schedule.csv tasks.csv resources.csv [calendar.csv]
python -m ccpm_scheduler.plot schedule.csv gantt.png --resources resources.csv \
    [--calendar calendar.csv]
```

Coming next (see [PLAN.md](PLAN.md)):

- **Phase 1b** — typed model (`Task`, `Resource`, `Schedule`, `ValidationReport`
  with machine-readable issue codes) and a stable library API
- **Phase 2** — the `ccpm-scheduler` CLI: subcommands, `--json` output,
  meaningful exit codes, a `schema` subcommand — designed for AI agents
- **Phase 3+** — the Claude skill drives this CLI; the
  [our-planner](https://github.com/rnwolf/our-planner) GUI imports the library

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
  (`critical`, `feeding-n`), and link notation (buffers attached via `:PB`/`:FB`)
- `summary.md` — critical chain, project duration, buffer sizes, promised
  completion date (= end of the project buffer)
- `gantt.png` — critical chain, feeding chains, buffers, dependency arrows,
  and a resource-utilization panel on the same time axis

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
