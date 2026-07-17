# lab-trials — CCPM schedule

- **Critical chain**: P1 Procure rig → P3 Install rig → P4 Calibrate → P5 Run trial A → P7 Report A
- **Critical chain length**: 24 working days (work finishes day 24)
- **Project buffer**: 24 days → **promised completion: day 48**
- **Buffer sizing**: CAP (Cut & Paste: buffer = Σ safety removed from the chain) — 5 of 5 critical-chain tasks have derived (single-point) safety estimates

| Feeding buffer | Protects | Size (days) | Derived estimates | Merges into |
|---|---|---|---|---|
| FB1 | P2 Write protocol | 5 | 1 of 1 | start of P5 Run trial A |
| FB2 | P2 Write protocol → P6 Run trial B → P8 Report B | 1 (method wanted 12) | 3 of 3 | start of the Finish milestone |

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
