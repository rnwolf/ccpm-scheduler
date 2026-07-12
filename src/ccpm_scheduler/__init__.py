"""ccpm-scheduler — deterministic Critical Chain Project Management scheduling.

Phase 1 API: the four pipeline stages as modules, extracted verbatim from the
ccpm-scheduler Claude skill's bundled scripts (behavior-preserving, guarded by
byte-identical golden tests).

    validate  — check a project network (tasks/resources/calendar) before scheduling
    build     — build the resource-leveled, buffered CCPM schedule
    check     — verify a produced schedule against the inputs
    plot      — render a buffer-aware Gantt chart PNG (requires matplotlib)

A typed model and a stable public API arrive in Phase 1b; the ccpm-scheduler
CLI arrives in Phase 2. Until then the modules are runnable directly:

    python -m ccpm_scheduler.validate tasks.csv resources.csv [calendar.csv]
    python -m ccpm_scheduler.build tasks.csv resources.csv --out-dir out
    python -m ccpm_scheduler.check out/schedule.csv tasks.csv resources.csv
    python -m ccpm_scheduler.plot out/schedule.csv gantt.png --resources resources.csv
"""

__version__ = "0.1.0"
