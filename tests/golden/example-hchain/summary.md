# example — CCPM schedule

- **Critical chain**: [A Spec](https://example.com/wiki/spec) → [B Build](https://example.com/tickets/build) → [D Integrate](https://example.com/tickets/integrate) → [F Commission](https://example.com/wiki/commissioning)
- **Critical chain length**: 30 working days (work finishes day 30)
- **Project buffer**: 15 days → **promised completion: day 45**
- **Buffer sizing**: HCHAIN (50% of chain length) — 4 of 4 critical-chain tasks have derived (single-point) safety estimates

| Feeding buffer | Protects | Size (days) | Derived estimates | Merges into |
|---|---|---|---|---|
| FB1 | [C Design](https://example.com/wiki/design) → [E Test rig](https://example.com/tickets/test-rig) | 5 | 2 of 2 | start of [F Commission](https://example.com/wiki/commissioning) |

Resource availability from `calendar.csv` is honored: tasks are placed contiguously around outage windows (grey blocks in the Gantt utilization panel), never split across them.

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
