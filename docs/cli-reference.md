# CLI Reference

The `ccpm-scheduler` command line interface is designed for both human users and automated AI agents.

```bash
ccpm-scheduler [subcommand] [options]
```

---

## Design Contract for AI Agents & Automation

- **Exit Code Contract**:
  - `0`: Success (valid input or check passed).
  - `1`: Domain validation or schedule verification error (the JSON report is still cleanly emitted to `stdout`).
  - `2`: Invocation or usage error (e.g. unknown argument, missing required file).
- **Machine-Readable Mode (`--json`)**: Outputs single structured JSON documents to `stdout`.
- **Deterministic**: Given identical inputs, `ccpm-scheduler` produces **byte-identical** CSVs, markdown summaries, and JSON reports every time.
- **Non-Interactive**: No interactive prompts, ANSI color codes, or terminal paging.

---

## Subcommands

### 1. `validate`

Validates a project network before attempting to build a schedule. Checks for syntax errors, missing resources, non-positive durations, fractional values, circular dependencies, and calendar conflicts.

```bash
ccpm-scheduler validate TASKS.csv RESOURCES.csv [CALENDAR.csv]
ccpm-scheduler validate project.json
cat project.json | ccpm-scheduler validate - --json
```

**Options**:
- `--calendar CALENDAR.csv`: Specify resource calendar availability file (for CSV inputs).
- `--json`: Output machine-readable JSON report.

---

### 2. `build`

Runs validation first, then constructs a resource-leveled, late-start schedule protected by Project and Feeding Buffers. Writes `schedule.csv` and `summary.md` to `--out-dir`.

```bash
ccpm-scheduler build TASKS.csv RESOURCES.csv --calendar CALENDAR.csv \
    --out-dir plan --title "Release v1.0" --buffer-method cap
```

**Options**:
- `--out-dir DIR`: Directory where outputs are written (default: `.`).
- `--title TITLE`: Project title used in report headers (default: `"CCPM schedule"`).
- `--buffer-method {cap,hchain,rsem}`: Sizing strategy for Project & Feeding Buffers:
  - `cap`: Cut & Paste (derived from safety removed per task) — **default**.
  - `hchain`: 50% of chain length (`ceil(0.5 * sum(optimal_duration))`).
  - `rsem`: Root-Squared Error Method (`ceil(sqrt(sum(delta^2)))`).

- `--calendar CALENDAR.csv`: Resource calendar file (for CSV inputs).
- `--json`: Print schedule statistics, output file paths, and full schedule array as JSON.

---

### 3. `check`

Re-verifies an existing schedule against its input network to guarantee logic integrity (verifies precedence constraints, resource leveling, calendar rules, and buffer placement).

```bash
ccpm-scheduler check plan/schedule.csv TASKS.csv RESOURCES.csv [CALENDAR.csv]
ccpm-scheduler check plan/schedule.csv project.json --json
```

**Options**:
- `--calendar CALENDAR.csv`: Resource calendar file.
- `--json`: Output machine-readable check report.

---

### 4. `plot`

Generates a publication-ready, buffer-aware Gantt chart PNG image, including dependency arrows and resource capacity utilization panels.

```bash
ccpm-scheduler plot plan/schedule.csv plan/gantt.png \
    --resources RESOURCES.csv --calendar CALENDAR.csv --title "Release v1.0"
```

**Options**:
- `--resources RESOURCES.csv`: Real resource capacities for utilization panel.
- `--calendar CALENDAR.csv`: Draw unavailable calendar periods as grey hatched blocks.
- `--title TITLE`: Chart header title.
- `--critical-label LABEL`: Legend text for critical chain bars (default: `"Critical chain"`).
- `--no-utilization`: Omit resource utilization panel.
- `--no-links`: Omit dependency arrows.
- `--json`: Print `{ "ok": true, "wrote": "plan/gantt.png" }`.

---

### 5. `graph`

Renders a standalone interactive network graph HTML page (powered by `vis-network` via CDN) with zero build step required.

```bash
ccpm-scheduler graph plan/schedule.csv plan/project-network.html \
    --tasks TASKS.csv --title "Release v1.0"
```

**Options**:
- `--tasks TASKS.csv`: Original tasks file to populate realistic vs. optimal duration tooltips.
- `--title TITLE`: Header title for interactive graph page.
- `--critical-label LABEL`: Legend text for critical chain nodes.
- `--json`: Print `{ "ok": true, "wrote": "plan/project-network.html" }`.

---

### 6. `schema`

Prints JSON Schema definitions for the system's data contracts.

```bash
ccpm-scheduler schema network   # JSON Schema for network input format
ccpm-scheduler schema schedule  # JSON Schema for schedule output format
ccpm-scheduler schema report    # JSON Schema for validation/check reports
```
