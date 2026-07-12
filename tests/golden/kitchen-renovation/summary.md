# kitchen-renovation — CCPM schedule

- **Critical chain**: K1 Demolition → K3 Plumbing → K6 Tiling → K4 Cabinets → K5 Worktops and finishing
- **Critical chain length**: 19 working days (work finishes day 22)
- **Project buffer**: 10 days → **promised completion: day 32**

| Feeding buffer | Protects | Size (days) | Merges into |
|---|---|---|---|
| FB1 | K2 Electrics | 2 | start of K4 Cabinets |

Resource availability from `calendar.csv` is honored: tasks are placed contiguously around outage windows (grey blocks in the Gantt utilization panel), never split across them.

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
