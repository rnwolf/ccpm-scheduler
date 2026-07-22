# ccpm-scheduler

Deterministic **Critical Chain Project Management (CCPM)** scheduling as a Python library and CLI — built for humans, AI agents, and integration into custom tools.

Give `ccpm-scheduler` a project network (tasks, dependencies, duration estimates, resource assignments) plus resource availability, and it produces a proper Critical Chain schedule: resource-leveled, scheduled as late as possible, protected by a project buffer and feeding buffers, complete with buffer-aware Gantt charts and interactive dependency network visualizations.

Same input always yields byte-identical output — the scheduler is fully deterministic, making it scriptable, diffable, and testable.

---

## Why This Utility?

`ccpm-scheduler` was created to make **Critical Chain Project Management (CCPM)** lightweight, open-source, and accessible to practitioners, software developers, and AI agents.

- **Free & Frictionless Onboarding**: Enterprise CCPM platforms are powerful, but evaluating CCPM can often involve vendor procurement, licensing costs, or complex server setups. `ccpm-scheduler` allows individuals, small teams, and researchers to experiment with and learn CCPM principles **completely free**, using simple text/CSV files or Python scripts.
- **Deterministic & Scriptable Engine**: Offers a lightweight CLI and Python API built for local automation, continuous integration, and seamless integration with AI agent workflows and custom tools (like `our-planner`).
- **Pathway to Commercial Solutions**: This utility serves as a starting point to prove the practical benefits of CCPM—such as aggressive task estimation, resource-leveled schedules, and aggregated buffer protection. Once organizations recognize these benefits and scale up to require enterprise features (e.g., real-time multi-user collaboration, portfolio-level fever chart tracking, and battle-tested enterprise infrastructure), they can smoothly transition to commercial CCPM software products.

---

## Key Features

- **Deterministic & Leveling**: Resource leveling ensures no resource is double-booked across concurrent tasks. Late-start scheduling maximizes project flexibility.
- **Selectable Buffer Sizing**: Supports three configurable buffer calculation methods for Project Buffers and Feeding Buffers:
    - **Cut & Paste (`cap`)** *(Default)*: Sum of safety removed from tasks in the protected chain (`sum(realistic - optimal)`).
    - **50% of Chain (`hchain`)**: Goldratt's classic 50% rule (`ceil(0.5 * sum(optimal_duration))`).
    - **Root-Squared Error (`rsem`)**: Statistical combination of task variances (`ceil(sqrt(sum(delta^2)))`).
- **CLI & Library API**: Use directly from terminal scripts, Python code, or AI agents.
- **Interactive Visualization**: Generates standalone interactive dependency network views (using `vis-network`) and Gantt chart image plots.
- **JSON & CSV Exchange Formats**: Supports clean, machine-readable inputs and outputs.

---

## Installation

Install using `pip` or `uv`:

```bash
pip install ccpm-scheduler
```

Or with `uv`:

```bash
uv add ccpm-scheduler
```

---

## Quickstart (CLI)

```bash
# Validate input files
ccpm-scheduler validate tasks.csv resources.csv calendar.csv

# Build a buffered schedule using Cut & Paste buffer sizing
ccpm-scheduler build tasks.csv resources.csv --calendar calendar.csv \
    --out-dir plan --title "Website Relaunch" --buffer-method cap

# Check schedule integrity
ccpm-scheduler check plan/schedule.csv tasks.csv resources.csv calendar.csv

# Plot Gantt chart and build interactive network graph
ccpm-scheduler plot plan/schedule.csv plan/gantt.png --resources resources.csv
ccpm-scheduler graph plan/schedule.csv plan/project-network.html \
    --tasks tasks.csv --title "Website Relaunch"
```

---

## Documentation Sections

- **[Walkthrough Examples](examples.md)**: Step-by-step example comparing traditional CPM vs. CCPM schedules and buffer sizing methods (`cap`, `hchain`, `rsem`).
- **[Core Concepts](concepts.md)**: CCPM theory, two-point estimates, late-start scheduling, and resource leveling.
- **[CLI Reference](cli-reference.md)**: Subcommands, options, exit code contract, and `--json` mode.
- **[Data Formats & Schemas](formats.md)**: Specification of CSV files, unified JSON Exchange Format, and output artifacts.
- **[Buffer Sizing](buffer-sizing.md)**: Deep dive into the theory, mathematics, and trade-offs of the `cap`, `hchain`, and `rsem` buffer calculation methods.
- **[Network Layout Engine](network-layout.md)**: Architectural documentation of the 6-step deterministic scheduling pipeline, ALAP baseline, resource leveling rules, and buffer insertion.
- **[Python API](python-api.md)**: Library functions, dataclasses, and machine-readable validation error codes.

- **[AI Agent & Tool Integration](agent-integration.md)**: Integration patterns for AI agents and GUI applications (like `our-planner`).
- **[Resources & References](references.md)**: Recommended books, articles, YouTube lectures, and external resources.
