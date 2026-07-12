# lab-trials — CCPM schedule

- **Critical chain**: P1 Procure rig → P3 Install rig → P4 Calibrate → P5 Run trial A → P7 Report A
- **Critical chain length**: 24 working days (work finishes day 24)
- **Project buffer**: 12 days → **promised completion: day 36**

| Feeding buffer | Protects | Size (days) | Merges into |
|---|---|---|---|
| FB1 | P2 Write protocol | 5 | start of P5 Run trial A |
| FB2 | P2 Write protocol → P6 Run trial B → P8 Report B | 1 | start of the Finish milestone |

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
