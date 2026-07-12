"""Typed data model for CCPM scheduling.

The model is deliberately tolerant on input: numeric fields hold whatever the
source provided (int, float, or unparseable string) so that `validate_network`
can report problems as structured issues instead of crashing mid-parse.
`as_int` is the single choke point that converts a raw value to the integer
the scheduling engine needs — it raises ValueError for fractional or
non-numeric values, which validation surfaces as E_FRACTIONAL_* / E_BAD_*
issues beforehand.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict


class CcpmError(Exception):
    """Unrecoverable input problem hit by an engine that assumes valid input.

    The engines (build/check/plot) expect a network that passed
    validate_network; when they trip over something anyway, they raise this
    with a human-readable message instead of a traceback.
    """


def as_int(value, what="value"):
    """Coerce a raw model value to int; reject fractional and non-numeric."""
    if isinstance(value, bool):
        raise ValueError(f"{what} must be a number (got {value!r})")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(f"{what} is fractional ({value!r}) — not supported in v1")
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        try:
            f = float(s)
        except ValueError:
            raise ValueError(f"{what} must be a number (got {value!r})") from None
        if f.is_integer():
            return int(f)
        raise ValueError(f"{what} is fractional ({value!r}) — not supported in v1") from None


@dataclass(frozen=True)
class Link:
    """One dependency link. type is FS/SS/FF/SF for input links; schedule rows
    additionally use the CCPM buffer types PB/FB."""
    pred_id: str
    type: str = "FS"
    lag: int = 0

    def render(self) -> str:
        s = self.pred_id
        if self.type != "FS":
            s += f":{self.type}"
        if self.lag:
            s += f"{self.lag:+d}"
        return s


@dataclass
class Task:
    id: str
    name: str | None = None
    realistic_duration: object = None   # estimate with safety included
    optimal_duration: object = None     # padding-free estimate
    links: list[Link] = field(default_factory=list)
    resource_ids: list[str] = field(default_factory=list)
    url: str = ""
    # fractional allocations (e.g. our-planner's {"r1": 0.5}) are carried so
    # validation can reject them with a precise message; v1 schedules whole
    # resources only
    allocations: dict[str, float] | None = None
    # original predecessor notation, preserved verbatim so it passes through
    # to schedule.csv unchanged; None means "synthesize from links"
    pred_str: str | None = None

    def __post_init__(self):
        if self.name is None:
            self.name = self.id

    @property
    def duration(self) -> int:
        """Scheduling duration: optimal estimate, else the classic 50% cut."""
        if self.optimal_duration not in (None, ""):
            return as_int(self.optimal_duration, f"task {self.id}: optimal_duration")
        if self.realistic_duration in (None, ""):
            raise CcpmError(f"task {self.id}: no duration given")
        return math.ceil(
            as_int(self.realistic_duration, f"task {self.id}: realistic_duration") / 2)

    def predecessor_notation(self) -> str:
        if self.pred_str is not None:
            return self.pred_str
        return ";".join(l.render() for l in self.links)


@dataclass
class Resource:
    id: str
    name: str | None = None
    capacity: object = 1
    url: str = ""

    def __post_init__(self):
        if self.name is None:
            self.name = self.id


@dataclass
class CalendarWindow:
    """Capacity override on the half-open day range [start, end)."""
    resource_id: str
    start: object
    end: object
    capacity: object


@dataclass
class Network:
    tasks: list[Task] = field(default_factory=list)
    resources: list[Resource] = field(default_factory=list)
    calendar: list[CalendarWindow] = field(default_factory=list)
    # True when a calendar was explicitly supplied (even an empty one) —
    # the build summary mentions calendar handling only in that case
    has_calendar: bool = False
    # non-semantic warnings collected while loading (e.g. legacy column names)
    io_warnings: list["Issue"] = field(default_factory=list)


ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    """One validation finding, machine-readable (code) and human-readable
    (message). severity is "error" or "warning"."""
    code: str
    severity: str
    message: str
    task_ids: tuple[str, ...] = ()
    resource_ids: tuple[str, ...] = ()

    def to_json(self) -> dict:
        return asdict(self) | {"task_ids": list(self.task_ids),
                               "resource_ids": list(self.resource_ids)}


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)
    start_tasks: list[str] = field(default_factory=list)     # no predecessors
    terminal_tasks: list[str] = field(default_factory=list)  # no successors

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code, message, task_ids=(), resource_ids=()):
        self.issues.append(Issue(code, ERROR, message,
                                 tuple(task_ids), tuple(resource_ids)))

    def warning(self, code, message, task_ids=(), resource_ids=()):
        self.issues.append(Issue(code, WARNING, message,
                                 tuple(task_ids), tuple(resource_ids)))

    def to_json(self) -> dict:
        return {"ok": self.ok,
                "issues": [i.to_json() for i in self.issues],
                "start_tasks": self.start_tasks,
                "terminal_tasks": self.terminal_tasks}


SCHEDULE_COLUMNS = ["id", "name", "type", "chain", "start", "finish",
                    "duration", "resource_ids", "predecessor_ids", "url"]

TYPE_TASK = "task"
TYPE_PROJECT_BUFFER = "project_buffer"
TYPE_FEEDING_BUFFER = "feeding_buffer"


@dataclass
class ScheduleRow:
    """One schedule.csv row. resource_ids and predecessor_ids keep the exact
    string notation used in the CSV (";"-joined; links as `B`, `B:SS+2`,
    buffers as `X:PB`/`X:FB`) so files round-trip byte-identically."""
    id: str
    name: str
    type: str            # task | project_buffer | feeding_buffer
    chain: str           # critical | feeding-<n> | none
    start: int
    finish: int
    duration: int
    resource_ids: str = ""
    predecessor_ids: str = ""
    url: str = ""

    def to_csv_dict(self) -> dict:
        return {c: getattr(self, c) for c in SCHEDULE_COLUMNS}

    def to_json(self) -> dict:
        return self.to_csv_dict()


@dataclass
class Schedule:
    rows: list[ScheduleRow] = field(default_factory=list)

    def row(self, row_id: str) -> ScheduleRow | None:
        for r in self.rows:
            if r.id == row_id:
                return r
        return None

    def to_json(self) -> dict:
        return {"rows": [r.to_json() for r in self.rows]}


@dataclass
class BuildStats:
    deadline: int                  # T at which leveling succeeded
    critical_chain: list[str]
    critical_chain_length: int    # working days
    project_buffer: int
    promise_day: int              # end of the project buffer
    merges: int
    buffered: int
    unprotected: int
    finish_milestone: bool

    def status_line(self, title: str) -> str:
        return (f"{title}: T={self.deadline}, "
                f"CC={'->'.join(self.critical_chain)} "
                f"({self.critical_chain_length}d), "
                f"PB={self.project_buffer}, promise=day {self.promise_day}, "
                f"{self.merges} merge(s), {self.buffered} buffered, "
                f"{self.unprotected} unprotected"
                + (", FINISH milestone" if self.finish_milestone else ""))


@dataclass
class BuildResult:
    schedule: Schedule
    summary_markdown: str
    title: str
    stats: BuildStats
