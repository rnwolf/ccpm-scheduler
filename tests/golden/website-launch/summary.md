# website-launch — CCPM schedule

- **Critical chain**: [W5 Build backend](https://example.com/tickets/W5) → [W4 Build frontend](https://example.com/tickets/W4) → [W6 Integrate](https://example.com/tickets/W6) → [W8 Load content](https://example.com/tickets/W8) → [W9 Launch QA](https://example.com/tickets/W9)
- **Critical chain length**: 23 working days (work finishes day 28)
- **Project buffer**: 23 days → **promised completion: day 51**
- **Buffer sizing**: CAP (Cut & Paste: buffer = Σ safety removed from the chain) — 5 of 5 critical-chain tasks have derived (single-point) safety estimates

| Feeding buffer | Protects | Size (days) | Derived estimates | Merges into |
|---|---|---|---|---|
| FB1 | [W3 Design mockups](https://example.com/tickets/W3) | 4 | 1 of 1 | start of [W4 Build frontend](https://example.com/tickets/W4) |
| FB2 | [W1 Content outline](https://example.com/tickets/W1) → [W2 Draft copy](https://example.com/tickets/W2) → [W7 Edit copy](https://example.com/tickets/W7) | 6 (method wanted 11) | 3 of 3 | start of [W8 Load content](https://example.com/tickets/W8) |

Resource availability from `calendar.csv` is honored: tasks are placed contiguously around outage windows (grey blocks in the Gantt utilization panel), never split across them.

Durations are optimal (padding-free) estimates; overruns are expected roughly half the time and consume buffer — the promise date only moves if a buffer runs dry. Work the critical chain relay-runner style: hand off immediately, no multitasking.
