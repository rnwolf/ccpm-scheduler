# Frequently Asked Questions (FAQ)

This page answers common questions about **ccpm-scheduler**'s scheduling behavior, buffer sizing algorithms, layout rules, and constraint enforcement.

---

## Buffer Placement & Sizing

### How does `ccpm-scheduler` deal with feeding buffers when feeding chains are equally long as (or land tight against) the Critical Chain?

When a feeding chain finishes tight against its merge point on the Critical Chain (or when project start / resource constraints prevent shifting the feeding chain earlier), attempting to force a full-sized feeding buffer could risk elongating the Critical Chain or pushing project start before Day 0.

`ccpm-scheduler` resolves this using **constrained backward shifting**, **gap absorption (pre-consumed buffers)**, and **unprotected merge detection**:

1. **Constrained Backward Shifting**: The scheduler first attempts to shift the feeding chain backward to open up space for the calculated feeding buffer size $M$, bounded by Day 0, predecessor links, and resource availability across all chains.
2. **Pre-Consumed Buffers & Gap Absorption (`N (method wanted M)`)**: If the feeding chain cannot shift far enough to fit the full calculated buffer $M$, `ccpm-scheduler` fits whatever gap $N$ is available ($0 < N < M$). It sets the buffer duration to $N$ days without extending the Critical Chain, and reports `N (method wanted M)` in `summary.md` and CLI build stats so the buffer shortfall is fully visible.
3. **Unprotected Merges (`gap = 0`)**: If the feeding chain finishes tight against its critical successor ($N = 0$) and cannot shift earlier at all, `ccpm-scheduler` enforces a policy to **never emit a zero-length (0-day) buffer row**. The buffer is omitted entirely and flagged in `summary.md` with an explicit warning:
   > *"Warning: the merge ... has no room for a feeding buffer — that path is effectively critical. Watch it as closely as the critical chain."*

For further details on buffer algorithms and layout mechanics, see [Buffer Sizing](buffer-sizing.md) and [Network Layout Engine](network-layout.md).

---

## Calendar & Time Resolution

### How does `ccpm-scheduler` handle non-working weekend days?

`ccpm-scheduler` operates at a **day-level resolution** and schedules tasks as contiguous blocks of days without automatically splitting individual tasks across weekend gaps.

During design, automatic task splitting across weekends was intentionally avoided for several core architectural reasons:

1. **Avoiding Task Splitting Complexity**: Splitting continuous tasks across non-working weekends creates fragmented task fragments, multi-segment schedule states, and fragile round-tripping when exchanging schedule data with downstream tools (e.g., GUI planners, visual Gantt charts, or CSV/JSON exchange format parsers).
2. **Day-Level Resolution**: The engine operates purely on integer day offsets (`start`, `finish`, `duration`).
3. **Estimate Recommendations**: Task duration estimates should be provided in calendar/elapsed days (including expected weekend days for multi-week efforts). Explicit resource availability limits (such as maintenance or holiday windows) are modeled using `calendar.csv`, where tasks shift contiguously around outage blocks without fragmenting task identity.

