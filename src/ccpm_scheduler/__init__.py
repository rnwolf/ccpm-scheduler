"""ccpm-scheduler — deterministic Critical Chain Project Management scheduling.

Library API (the four pipeline stages plus the typed model):

    from ccpm_scheduler import (load_network, network_from_json,
                                validate_network, build_schedule,
                                check_schedule, plot_schedule)

    network = load_network("tasks.csv", "resources.csv", "calendar.csv")
    report = validate_network(network)      # -> ValidationReport (coded Issues)
    if report.ok:
        result = build_schedule(network, title="My project")   # -> BuildResult
        assert check_schedule(result.schedule, network).ok
        plot_schedule(result.schedule, "gantt.png",
                      resources=network.resources, calendar=network.calendar)

Networks can also come from the JSON exchange format (network_from_json /
network_to_json) — see ccpm_scheduler.io for the format. Validation issues
carry machine-readable codes (E_CYCLE, E_NO_RESOURCE,
E_FRACTIONAL_ALLOCATION, ...) plus the offending task/resource ids, so
embedding tools can annotate their own UI.

The modules are also runnable directly:

    python -m ccpm_scheduler.validate tasks.csv resources.csv [calendar.csv]
    python -m ccpm_scheduler.build tasks.csv resources.csv --out-dir out
    python -m ccpm_scheduler.check out/schedule.csv tasks.csv resources.csv
    python -m ccpm_scheduler.plot out/schedule.csv gantt.png --resources resources.csv

The `ccpm-scheduler` CLI wraps all of this — see `ccpm-scheduler --help`.
"""

# Single-sourced from pyproject.toml via the installed package metadata, so
# the runtime version can never drift from the published one again (0.4.0
# shipped reporting 0.3.1 because this used to be a duplicated literal).
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("ccpm-scheduler")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0+unknown"

from .model import (                                        # noqa: F401
    CcpmError, Link, Task, Resource, CalendarWindow, Network,
    Issue, ValidationReport, Schedule, ScheduleRow,
    BuildResult, BuildStats, SCHEDULE_COLUMNS,
    TYPE_TASK, TYPE_PROJECT_BUFFER, TYPE_FEEDING_BUFFER,
)
from .io import (                                           # noqa: F401
    load_network, load_tasks, load_resources, load_calendar, load_schedule,
    network_from_json, network_to_json, schedule_from_json,
    write_schedule_csv, write_build_outputs,
)
from .validate import validate_network                      # noqa: F401
from .build import build_schedule                           # noqa: F401
from .check import check_schedule                           # noqa: F401
from .graph import render_network_html, write_network_html  # noqa: F401

__all__ = [
    "CcpmError", "Link", "Task", "Resource", "CalendarWindow", "Network",
    "Issue", "ValidationReport", "Schedule", "ScheduleRow",
    "BuildResult", "BuildStats", "SCHEDULE_COLUMNS",
    "TYPE_TASK", "TYPE_PROJECT_BUFFER", "TYPE_FEEDING_BUFFER",
    "load_network", "load_tasks", "load_resources", "load_calendar", "load_schedule",
    "network_from_json", "network_to_json", "schedule_from_json",
    "write_schedule_csv", "write_build_outputs",
    "validate_network", "build_schedule", "check_schedule", "plot_schedule",
    "render_network_html", "write_network_html",
    "__version__",
]


def plot_schedule(*args, **kwargs):
    """Lazy proxy for ccpm_scheduler.plot.plot_schedule — importing the real
    thing pulls in matplotlib, which library consumers may not need."""
    from .plot import plot_schedule as _plot
    return _plot(*args, **kwargs)
