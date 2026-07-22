# Python Library API

The `ccpm_scheduler` Python package exposes a pure Python library API for loading, validating, building, verifying, and visualizing CCPM schedules programmatically.

```python
from ccpm_scheduler import (
    load_network,
    validate_network,
    build_schedule,
    check_schedule,
    plot_schedule,
    write_network_html,
)

# 1. Load network
network = load_network("tasks.csv", "resources.csv", "calendar.csv")

# 2. Validate network
report = validate_network(network)
if report.ok:
    # 3. Build schedule
    result = build_schedule(network, title="Website Relaunch", buffer_method="cap")
    
    # 4. Verify schedule
    assert check_schedule(result.schedule, network).ok
    
    # 5. Render outputs
    plot_schedule(result.schedule, "gantt.png", resources=network.resources)
    write_network_html(result.schedule, "network.html", title="Website Relaunch")
```

---

## Core Pipeline Functions

### `load_network(tasks_path, resources_path, calendar_path=None) -> Network`
Loads a project network from CSV files into a typed `Network` model.

### `network_from_json(json_str_or_dict) -> Network`
Parses a JSON string or dict in the unified exchange format into a typed `Network` model.

### `network_to_json(network: Network) -> dict`
Serializes a `Network` instance into the unified JSON exchange dictionary.

### `validate_network(network: Network) -> ValidationReport`
Validates network logic and returns a `ValidationReport` containing structured `Issue` records. Does not raise exceptions on invalid networks; check `report.ok` or `report.errors`.

### `build_schedule(network: Network, title: str = "CCPM schedule", buffer_method: str = "cap") -> BuildResult`
Executes resource leveling, late-start scheduling, Critical Chain identification, and buffer sizing. Returns a `BuildResult` dataclass containing `schedule`, `summary_markdown`, `title`, and `stats`.

### `check_schedule(schedule: Schedule, network: Network) -> ValidationReport`
Re-verifies an existing `Schedule` object against its source `Network`. Returns a `ValidationReport` with any structural or resource capacity violations found.

### `plot_schedule(schedule, out_path, title=..., resources=..., calendar=...)`
Renders a buffer-aware Gantt chart PNG image. Matplotlib is loaded lazily only when this function is invoked.

### `write_network_html(schedule, out_path, title=..., tasks=...)`
Writes an interactive HTML dependency graph using embedded data and `vis-network`.

---

## Key Data Models

### `Task`
Dataclass representing one project task.
- `id: str`
- `name: str | None`
- `realistic_duration: object` (working days estimate with safety)
- `optimal_duration: object` (padding-free working days estimate)
- `links: list[Link]` (predecessor links)
- `resource_ids: list[str]` (assigned resources)

### `Resource`
- `id: str`
- `name: str | None`
- `capacity: object` (integer capacity per day, default `1`)

### `ValidationReport`
- `ok: bool`: True if there are zero errors (warnings are permitted).
- `issues: list[Issue]`: List of all validation issues.
- `errors: list[Issue]`: Filtered list of issues where `severity == "error"`.
- `warnings: list[Issue]`: Filtered list of issues where `severity == "warning"`.
- `start_tasks: list[str]`: Task IDs with no predecessors.
- `terminal_tasks: list[str]`: Task IDs with no successors.

### `Issue`
- `code: str`: Machine-readable error or warning code.
- `severity: str`: `"error"` or `"warning"`.
- `message: str`: Human-readable explanation.
- `task_ids: tuple[str, ...]`: Offending task IDs.
- `resource_ids: tuple[str, ...]`: Offending resource IDs.

---

## Machine-Readable Validation Codes

When embedding `ccpm-scheduler` into custom UIs or agent applications, inspect `Issue.code` to surface structured errors:

| Code | Severity | Description |
|---|---|---|
| `E_DUP_TASK` | Error | Duplicate task ID found in network. |
| `E_DUP_RESOURCE` | Error | Duplicate resource ID found in network. |
| `E_UNKNOWN_PRED` | Error | Task references a predecessor ID that does not exist. |
| `E_MALFORMED_LINK` | Error | Predecessor link syntax is invalid (e.g. `A:XX`). |
| `E_CYCLE` | Error | Circular dependency detected (cycle path provided in message). |
| `E_BAD_DURATION` | Error | Task duration is non-numeric or less than 1 (`< 1`). |
| `E_FRACTIONAL_DURATION` | Error | Task duration is fractional (v1 requires integer working days). |
| `E_FRACTIONAL_CAPACITY` | Error | Resource capacity is fractional (v1 requires integer units). |
| `E_FRACTIONAL_ALLOCATION` | Error | Task allocates partial resource capacity (e.g. `0.5`). |
| `E_NO_RESOURCE` | Error | Task has no resources assigned (cannot contend for leveling). |
| `E_UNKNOWN_RESOURCE` | Error | Task assigned to a resource ID not listed in resources. |
| `E_BAD_CAPACITY` | Error | Resource capacity is less than 1 (`< 1`). |
| `E_CAL_BAD_ROW` | Error | Calendar window contains unparseable values. |
| `E_CAL_UNKNOWN_RESOURCE` | Error | Calendar window targets unknown resource ID. |
| `E_CAL_EMPTY_RANGE` | Error | Calendar window `from >= to`. |
| `E_CAL_NEG_CAPACITY` | Error | Calendar window capacity is less than 0 (`< 0`). |
| `E_CAL_OVERLAP` | Error | Overlapping calendar windows for the same resource. |
| `W_CAPACITY_GT1` | Warning | Resource capacity is greater than 1 (`> 1`) (unusual in CCPM environments). |
| `W_NON_FS_LINK` | Warning | Non-Finish-to-Start link used (SS, FF, SF). |
