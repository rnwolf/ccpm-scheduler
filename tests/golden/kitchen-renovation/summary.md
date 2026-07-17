# kitchen-renovation — CCPM schedule

- **Critical chain**: K1 Demolition → K3 Plumbing → K6 Tiling → K4 Cabinets → K5 Worktops and finishing
- **Critical chain length**: 19 working days (work finishes day 22)
- **Project buffer**: 19 days → **promised completion: day 41**
- **Buffer sizing**: CAP (Cut & Paste: buffer = Σ safety removed from the chain) — 5 of 5 critical-chain tasks have derived (single-point) safety estimates

| Feeding buffer | Protects | Size (days) | Derived estimates | Merges into |
|---|---|---|---|---|
| FB1 | K2 Electrics | 3 | 1 of 1 | start of K4 Cabinets |

Resource availability from `calendar.csv` is honored: tasks are placed contiguously around outage windows (grey blocks in the Gantt utilization panel), never split across them.

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
