# equipment-retrofit — CCPM schedule

- **Critical chain**: R1 Strip down machine → R4 Paint frame → R7 Install panels → R3 Refurbish spindle → R6 Install spindle → R9 Commission → R10 Document and handover
- **Critical chain length**: 23 working days (work finishes day 23)
- **Project buffer**: 12 days → **promised completion: day 35**

| Feeding buffer | Protects | Size (days) | Merges into |
|---|---|---|---|
| FB1 | R2 Order parts | 6 | start of R6 Install spindle |
| FB2 | R5 Upgrade wiring → R8 Wire cabinet | 5 | start of R9 Commission |

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
