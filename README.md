# ccpm-scheduler

Deterministic Critical Chain Project Management (CCPM) scheduling as a Python library and CLI — built for humans, AI agents, and integration with project management tools.

[![PyPI Version](https://img.shields.io/pypi/v/ccpm-scheduler.svg)](https://pypi.org/project/ccpm-scheduler/)
[![Python Versions](https://img.shields.io/pypi/pyversions/ccpm-scheduler.svg)](https://pypi.org/project/ccpm-scheduler/)
[![License](https://img.shields.io/badge/license-MIT%2FApache--2.0-blue.svg)](#license)

Give `ccpm-scheduler` a project network (tasks, dependencies, duration estimates, resource assignments) plus resource availability, and it produces a proper **Critical Chain schedule**:
- **Resource-Leveled**: Resolves resource contention so no resource is over-allocated.
- **As-Late-As-Possible (ALAP) Scheduling**: Eliminates Parkinson's Law by scheduling non-critical work to finish just when needed.
- **Protected by Buffers**: Insulates project completion with a **Project Buffer** and protects merge points with **Feeding Buffers**.
- **Buffer-Aware Visualizations**: Generates rich Gantt charts (`.png`) and interactive standalone web dependency graphs (`.html`).
- **Fully Deterministic**: The same input always produces byte-identical schedule outputs — ideal for automation, scripting, and CI/CD pipelines.

---

## Quickstart

### Installation

Install via `pip` or run instantly with `uv`:

```bash
# Install via pip
pip install ccpm-scheduler

# Or run directly without installation via uv
uvx ccpm-scheduler --help
```

---

## Status & Roadmap

All primary development phases outlined in [PLAN.md](PLAN.md) (Phases 1 through 6) are **fully complete**, including:
- Behaviour-preserving core engine and typed data model.
- Agent-friendly CLI with machine-readable `--json` contracts.
- Integration with AI agents (Claude skills) and GUI planners ([our-planner](https://github.com/rnwolf/our-planner)).
- Selectable buffer-sizing methods (`cap` Cut & Paste, `hchain` 50% chain, `rsem` root-squared error).

### Future Direction: Fractional Resource Assignments
Currently, `ccpm-scheduler` enforces whole-resource allocations (1.0 capacity per task). **Fractional resource assignments** (e.g. allocating `0.5` FTE of a resource to a task) are identified as the primary area for future improvement. Future decisions on fractional leveling algorithms will be guided by feedback from real-world usage and community input.

---

## CLI Usage

Built for humans *and* AI agents: exit codes form a strict contract (`0` = ok, `1` = validation or schedule issue with structured report, `2` = usage error), `--json` prints machine-readable JSON documents, and outputs are strictly deterministic.

```bash
# 1. Validate a project network
ccpm-scheduler validate tasks.csv resources.csv calendar.csv

# 2. Build a resource-leveled, buffered schedule
ccpm-scheduler build tasks.csv resources.csv --calendar calendar.csv \
    --out-dir plan --title "Website relaunch" --buffer-method cap

# 3. Verify schedule integrity against project constraints
ccpm-scheduler check plan/schedule.csv tasks.csv resources.csv calendar.csv

# 4. Plot a buffer-aware Gantt chart with resource utilization
ccpm-scheduler plot plan/schedule.csv plan/gantt.png --resources resources.csv

# 5. Generate an interactive web graph visualization
ccpm-scheduler graph plan/schedule.csv plan/project-network.html \
    --tasks tasks.csv --title "Website relaunch"

# 6. Inspect machine-readable JSON Schemas
ccpm-scheduler schema network
```

### JSON Input & Pipe Support
Networks can be passed as CSV files or as a single JSON document (via file path or `-` for stdin):

```bash
echo '{"tasks": [...], "resources": [...]}' | ccpm-scheduler build - --json
```

---

## Library API

Import `ccpm-scheduler` directly into Python applications:

```python
from ccpm_scheduler import (
    load_network,
    validate_network,
    build_schedule,
    check_schedule,
    plot_schedule,
)

# Load network from CSV or JSON
network = load_network("tasks.csv", "resources.csv", "calendar.csv")

# Validate network rules (cycle detection, resource assignment, duration checks)
report = validate_network(network)
if report.ok:
    # Build schedule using Cut & Paste (cap) buffer sizing
    result = build_schedule(network, title="My Project", buffer_method="cap")
    
    # Verify schedule rules
    assert check_schedule(result.schedule, network).ok
    
    # Plot Gantt chart
    plot_schedule(
        result.schedule,
        "gantt.png",
        resources=network.resources,
        calendar=network.calendar,
    )
    print(result.stats.status_line("My Project"))
```

---

## File Contracts

### Input Format
- **`tasks.csv`**: `id, name, realistic_duration, optimal_duration (optional), predecessor_ids, resource_ids, url (optional)`
  - `realistic_duration`: Estimate including safety margin.
  - `optimal_duration`: Padding-free duration. If omitted, the classic 50% safety cut is applied automatically.
  - `predecessor_ids`: Semicolon-separated links (`A`, `A:SS+2`, `A:FF`, `A:SF`).
  - `resource_ids`: Semicolon-separated resource IDs assigned to the task.
- **`resources.csv`**: `id, name, capacity, url (optional)` (capacity defaults to 1).
- **`calendar.csv`** (optional): `resource_id, from, to, capacity`: Overrides resource capacity on half-open day intervals `[from, to)`.

### Output Format
- **`schedule.csv`**: Scheduled tasks and buffers with start/finish dates, chain designations (`critical`, `feeding-n`), and link attachments (`:PB`, `:FB`).
- **`summary.md`**: Project summary documenting critical chain duration, project buffer size, feeding buffers, promised completion date, and buffer calculation method (`cap`, `hchain`, `rsem`).
- **`gantt.png`**: High-resolution Gantt chart showing critical chain, feeding chains, buffers, dependencies, and daily resource utilization.
- **`project-network.html`**: Standalone interactive HTML graph (Vis-network) allowing zooming, panning, node dragging, and resource filtering.

---

## Development & Testing

We welcome contributions! The repository uses [`uv`](https://github.com/astral-sh/uv) for fast dependency management and [`prek`](https://github.com/jseris/prek) for git pre-commit checks.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/rnwolf/ccpm-scheduler.git
cd ccpm-scheduler

# Install development dependencies in virtualenv
uv sync

# Run the test suite with coverage report
uv run pytest

# Run pre-commit checks (ruff check & ruff format)
prek run --all-files
```

### Dev Dependencies & Tooling
- **Test Runner & Coverage**: `pytest`, `pytest-cov` (unit, integration, and CLI contract testing with coverage reports).
- **Property-Based Testing**: `hypothesis` (generates random DAG project networks to test scheduling invariants).
- **Linter & Formatter**: `ruff` (fast linting and code formatting).
- **Pre-commit Hooks**: `prek` (verifies ruff rules before git commits).

---

## Feedback, Suggestions & Issues

If you encounter tool errors, engine bugs, or have suggestions for improvements (such as real-world use cases for fractional resource assignments), please open an issue on GitHub:

👉 **[Submit a GitHub Issue](https://github.com/rnwolf/ccpm-scheduler/issues)**

When reporting bugs, please attach your project input (`tasks.csv`, `resources.csv`, or anonymized JSON) and the error report emitted by `--json` to help us diagnose and resolve the issue quickly.

---

## License

Dual-licensed under either of [MIT](LICENSE-MIT) or [Apache License 2.0](LICENSE-APACHE), at your option.
