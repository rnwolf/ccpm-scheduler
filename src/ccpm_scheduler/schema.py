"""JSON Schemas for the CLI's machine-readable contracts.

`ccpm-scheduler schema [network|schedule|report]` emits these so an agent (or
any tool) can discover the input/output shapes without reading source code.
"""

_ID = {
    "type": ["string", "number"],
    "description": "Identifier; numbers are coerced to strings.",
}

_LINK_NOTATION = (
    "Dependency link notation: a bare id means Finish-to-Start (`B`); typed "
    "links with optional integer lag are `B:SS+2`, `B:FF`, `B:SF-1`. "
    "Multiple links are separated by `;`."
)

NETWORK_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/rnwolf/ccpm-scheduler/schema/network.json",
    "title": "CCPM project network (input)",
    "description": (
        "A project network for CCPM scheduling: tasks with duration "
        "estimates, dependencies, and resource assignments, plus resource "
        "capacities and optional per-day availability overrides. Durations "
        "are whole working days; the schedule uses integer day offsets from "
        "day 0."
    ),
    "type": "object",
    "required": ["tasks", "resources"],
    "properties": {
        "tasks": {"type": "array", "items": {"$ref": "#/$defs/task"}},
        "resources": {"type": "array", "items": {"$ref": "#/$defs/resource"}},
        "calendar": {
            "type": "array",
            "items": {"$ref": "#/$defs/window"},
            "description": (
                "Optional per-day capacity overrides. Each window overrides a "
                "resource's capacity on the half-open day range [from, to); "
                "capacity 0 means unavailable. Tasks execute contiguously — "
                "they never pause across an outage."
            ),
        },
        "buffer_method": {
            "enum": ["cap", "hchain", "rsem"],
            "description": (
                "Optional buffer-sizing method for both buffer types "
                "(default cap). cap = Cut & Paste (buffer = sum of safety "
                "removed from the protected chain), hchain = 50% of chain "
                "length, rsem = root-squared error. A --buffer-method CLI "
                "flag overrides this key. See docs/buffer-sizing.md."
            ),
        },
    },
    "$defs": {
        "task": {
            "type": "object",
            "required": ["id"],
            "description": (
                "One task. Give realistic_duration (estimate with safety "
                "included) and/or optimal_duration (padding-free estimate). "
                "If optimal_duration is missing it is derived as "
                "ceil(realistic_duration / 2) — the classic 50% cut."
            ),
            "properties": {
                "id": _ID,
                "name": {"type": "string"},
                "realistic_duration": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "description": "Whole working days, safety included.",
                },
                "optimal_duration": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                    "description": "Whole working days, padding-free.",
                },
                "predecessors": {
                    "description": _LINK_NOTATION
                    + (" Also accepted: a list of tokens, or a list of {id, type, lag} objects."),
                    "oneOf": [
                        {"type": "string"},
                        {
                            "type": "array",
                            "items": {
                                "oneOf": [
                                    {"type": "string"},
                                    {
                                        "type": "object",
                                        "required": ["id"],
                                        "properties": {
                                            "id": _ID,
                                            "type": {"enum": ["FS", "SS", "FF", "SF"]},
                                            "lag": {"type": "integer"},
                                        },
                                    },
                                ]
                            },
                        },
                    ],
                },
                "resources": {
                    "description": (
                        "Resource ids this task needs — at least one, or the "
                        "task cannot contend for capacity. A map of "
                        "id -> allocation is accepted, but every allocation "
                        "must be exactly 1 in v1 (whole resources only)."
                    ),
                    "oneOf": [
                        {"type": "array", "items": _ID},
                        {"type": "object", "additionalProperties": {"type": "number"}},
                        {"type": "string"},
                    ],
                },
                "url": {
                    "type": "string",
                    "description": "Optional link to detail (ticket, wiki); passed through to outputs.",
                },
            },
        },
        "resource": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": _ID,
                "name": {"type": "string"},
                "capacity": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                    "description": "Concurrent tasks this resource can work "
                    "(whole units in v1; >1 is unusual in CCPM).",
                },
                "url": {"type": "string"},
            },
        },
        "window": {
            "type": "object",
            "required": ["resource_id", "from", "to", "capacity"],
            "properties": {
                "resource_id": _ID,
                "from": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "First day of the override (included).",
                },
                "to": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "End of the override (excluded).",
                },
                "capacity": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Effective capacity on [from, to); 0 = unavailable.",
                },
            },
        },
    },
}

SCHEDULE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/rnwolf/ccpm-scheduler/schema/schedule.json",
    "title": "CCPM schedule (output)",
    "description": (
        "The built schedule: every task plus buffer rows. Buffers attach via "
        "the CCPM-specific :PB/:FB link types — they are not work; during "
        "execution a buffer's END stays anchored and predecessor slippage "
        "consumes the buffer instead of pushing it. The promised completion "
        "date is the project buffer's finish."
    ),
    "type": "object",
    "required": ["rows"],
    "properties": {
        "rows": {"type": "array", "items": {"$ref": "#/$defs/row"}},
    },
    "$defs": {
        "row": {
            "type": "object",
            "required": ["id", "type", "chain", "start", "finish", "duration"],
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "type": {"enum": ["task", "project_buffer", "feeding_buffer"]},
                "chain": {
                    "type": "string",
                    "description": "critical | feeding-<n> | none",
                },
                "start": {"type": "integer", "minimum": 0},
                "finish": {"type": "integer", "minimum": 0},
                "duration": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "The scheduled (optimal) duration.",
                },
                "realistic_duration": {
                    "type": ["integer", "null"],
                    "description": "The task's realistic estimate (safety "
                    "included) when known; null for buffers, "
                    "milestones, and tasks that only gave an "
                    "optimal estimate. Compare against "
                    "duration to audit how much safety moved "
                    "into the chain's buffer.",
                },
                "resource_ids": {
                    "type": "string",
                    "description": "';'-separated resource ids (empty for buffers and milestones).",
                },
                "predecessor_ids": {
                    "type": "string",
                    "description": _LINK_NOTATION
                    + (
                        " Schedule rows additionally use :PB (project buffer "
                        "attachment) and :FB (feeding buffer attachment/merge)."
                    ),
                },
                "url": {"type": "string"},
            },
        },
    },
}

REPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://github.com/rnwolf/ccpm-scheduler/schema/report.json",
    "title": "Validation report (output of validate/check --json)",
    "type": "object",
    "required": ["ok", "issues"],
    "properties": {
        "ok": {
            "type": "boolean",
            "description": "True when there are no error-severity issues.",
        },
        "errors": {"type": "integer"},
        "warnings": {"type": "integer"},
        "issues": {"type": "array", "items": {"$ref": "#/$defs/issue"}},
        "start_tasks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tasks with no predecessors.",
        },
        "terminal_tasks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tasks with no successors.",
        },
    },
    "$defs": {
        "issue": {
            "type": "object",
            "required": ["code", "severity", "message"],
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Machine-readable issue code, stable "
                    "across versions (E_* = error, W_* = "
                    "warning), e.g. E_CYCLE, E_NO_RESOURCE, "
                    "E_FRACTIONAL_ALLOCATION.",
                },
                "severity": {"enum": ["error", "warning"]},
                "message": {
                    "type": "string",
                    "description": "Human-readable explanation, including how to fix.",
                },
                "task_ids": {"type": "array", "items": {"type": "string"}},
                "resource_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

SCHEMAS = {
    "network": NETWORK_SCHEMA,
    "schedule": SCHEDULE_SCHEMA,
    "report": REPORT_SCHEMA,
}
