# equipment-retrofit — CCPM schedule

- **Critical chain**: R1 Strip down machine → R4 Paint frame → R7 Install panels → R3 Refurbish spindle → R6 Install spindle → R9 Commission → R10 Document and handover
- **Critical chain length**: 23 working days (work finishes day 23)
- **Project buffer**: 23 days → **promised completion: day 46**
- **Buffer sizing**: CAP (Cut & Paste: buffer = Σ safety removed from the chain) — 7 of 7 critical-chain tasks have derived (single-point) safety estimates

| Feeding buffer | Protects | Size (days) | Derived estimates | Merges into |
|---|---|---|---|---|
| FB1 | R2 Order parts | 6 | 1 of 1 | start of R6 Install spindle |
| FB2 | R5 Upgrade wiring → R8 Wire cabinet | 5 (method wanted 9) | 2 of 2 | start of R9 Commission |

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
