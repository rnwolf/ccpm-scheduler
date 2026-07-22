# Buffer sizing methods

How the project buffer and each feeding buffer get their size. The *placement* of buffers
(critical chain identification, merge points, gap handling) is method-independent and described
in the README; this page covers only the sizing arithmetic, the three supported methods, and how
each behaves when task estimates are two-point, single-point, or a mixture.

**Why offer more than one method?** No sizing formula is "correct" — the research literature has
argued for decades without settling it. The real benefit of CCPM buffers is behavioral: a pooled,
visible protection that focuses execution attention on the tasks that threaten the promise date.
A team that rejects the plan because the buffer formula feels arbitrary never gets those
benefits. Offering the standard methods (and defaulting to the most explainable one) removes an
adoption obstacle; the buffer can always be manually resized in our-planner before a project
enters execution.

## Estimate normalization (shared by every method)

Each task carries up to two estimates:

- `realistic_duration` — the *safe* estimate, safety included (what people naturally give).
- `optimal_duration` — the *aggressive* / padding-free estimate (≈ 50% confidence).

Before any buffer arithmetic, every task is normalized to a triple **(optimal, realistic, Δ)**:

| Estimates given          | optimal            | realistic          | Δ (safety)          |
|--------------------------|--------------------|--------------------|----------------------|
| both                     | as given           | as given           | realistic − optimal  |
| realistic only           | ⌈realistic / 2⌉ (the classic 50% cut) | as given | realistic − ⌈realistic/2⌉ |
| optimal only             | as given           | 2 × optimal (derived, inverse of the cut) | optimal |

Tasks are always **scheduled at their optimal duration** regardless of method — the methods
differ only in how Δ (or chain length) is aggregated into a buffer. In a mixed network the
normalization is per-task, so two-point tasks contribute their *stated* safety and single-point
tasks contribute a *derived* (mechanical 50%) safety to the same sum.

> **Mixed-network caveat:** CAP and RSEM are only as informative as the Δs they aggregate. When
> most Δs are derived rather than estimated, both methods degrade toward mechanical 50%
> assumptions — the summary should report how many tasks in each protected chain had derived
> estimates, so the user knows how much to trust the number.

Buffers protect a **chain**: the critical chain for the project buffer, the feeding chain (or,
for extra merge edges, the feeder's backward non-critical closure) for a feeding buffer. In the
formulas below, sums run over the tasks of the protected chain. All results round up (`ceil`);
zero-length feeding buffers are never emitted (the merge is flagged unprotected instead).

## The methods

### CAP — Cut & Paste (default)

> Buffer = Σ Δᵢ

Goldratt's original method: every estimate contains embedded safety; remove it from each task
(schedule at optimal) and paste the *sum of what was removed* after the chain as the buffer.

- **Two-point estimates**: the buffer is exactly the safety the team said their tasks carried,
  pooled. Promise date = optimal chain + Σ Δ.
- **Single-point (realistic only)**: Δᵢ ≈ 50% of each task, so the buffer roughly equals the
  scheduled chain length, and the promise date lands back at the *original* realistic chain
  length — same date a traditional plan would promise, but with all protection pooled and
  visible instead of hidden inside tasks.
- **Mixed**: stated Δs and derived Δs sum together; the more two-point estimates, the more the
  buffer reflects real per-task uncertainty.

**Pros**: trivially explainable ("we didn't delete your safety — we pooled it"), which is why it
is the default: teams new to CCPM can verify the arithmetic against their own estimates. Respects
per-task uncertainty. Never under-protects relative to what the team estimated.
**Cons**: grows linearly with chain length — no statistical aggregation benefit, so long chains
are over-protected (the promise date gives back everything the cut gained). Plans look no shorter
than traditional ones (only the *behavior* differs).

### HCHAIN — 50% of chain length

> Buffer = ⌈0.5 × Σ optimalᵢ⌉

The most common textbook rule: the buffer is half the protected chain's scheduled length.


- **Two-point estimates**: Δs are *ignored* — a chain of tight estimates and a chain of wild
  guesses of equal length get identical buffers. This is the method's central weakness: it
  treats every task as equally uncertain.
- **Single-point**: with optimal derived as realistic/2, the buffer is ~25% of the realistic
  chain, and the promise date lands at ~75% of the traditional plan length.
- **Mixed**: only the optimal durations matter; the estimate mix changes nothing.

**Pros**: dead simple; produces visibly shorter plans (~75% of traditional), which sells CCPM's
schedule-compression story; buffer scales with chain length so it never vanishes.
**Cons**: ignores all uncertainty information (the user-visible symptom that motivated
alternatives); still linear in chain length, so statistically over-protects long chains while
potentially under-protecting short chains of high-variance tasks.

### RSEM — Root-Squared Error Method

> Buffer = ⌈√(Σ Δᵢ²)⌉

Treats each task's Δ as ~2 standard deviations of its duration uncertainty and pools
independent uncertainties the statistical way: the buffer is the root of the summed squares
(equivalently 2·√(Σ(Δᵢ/2)²)). See the
[PM Knowledge Center description](http://www.pmknowledgecenter.com/dynamic_scheduling/risk/sizing-ccbm-buffers-root-squared-error-method).

- **Two-point estimates**: the intended use — the buffer grows with √n rather than n, so long
  chains are not over-protected the way CAP/HCHAIN over-protect them.
- **Single-point**: Δᵢ = derived 50% cuts, so the formula runs on mechanical inputs — the result
  is a √n-scaled version of CAP with no real information gain. Usable, but the caveat above
  applies in full.
- **Mixed**: works per the normalization; derived-Δ tasks dilute the statistical meaning.

**Pros**: statistically grounded aggregation; per-task uncertainty matters; long chains get
proportionally smaller (cheaper) buffers.
**Cons**: assumes task uncertainties are independent — correlated risks (same person, same
unknown technology) make it under-protect; small task counts produce buffers that can feel
alarmingly thin to newcomers; hardest of the three to explain.

## Worked example

A critical chain of four tasks, two estimated two-point, two single-point:

| Task | realistic | optimal | Δ | note |
|------|-----------|---------|---|------|
| A    | 10        | 6       | 4  | stated |
| B    | 20        | 10      | 10 | stated |
| C    | 10        | (5)     | 5  | derived: ⌈10/2⌉ |
| D    | 20        | (10)    | 10 | derived: ⌈20/2⌉ |

Scheduled (optimal) chain = 31 days; traditional (realistic) plan = 60 days.

| Method | Buffer | Promise date |
|--------|--------|--------------|
| CAP    | 4+10+5+10 = **29** | day 60 (= the traditional plan, protection pooled) |
| HCHAIN | ⌈0.5 × 31⌉ = **16** | day 47 |
| RSEM   | ⌈√(4²+10²+5²+10²)⌉ = ⌈√241⌉ = **16** | day 47 |

The HCHAIN/RSEM tie here is a coincidence of the numbers. The scaling difference shows on
uniform chains — n tasks, each optimal 5, Δ 5:

| n | CAP | HCHAIN | RSEM |
|---|-----|--------|------|
| 2 | 10  | 5      | 8    |
| 6 | 30  | 15     | 13   |

RSEM out-buffers HCHAIN on short chains and under-buffers it on long ones — that is the √n
aggregation at work.

## Selecting a method

- CLI: `ccpm-scheduler build ... --buffer-method {cap,hchain,rsem}` — default `cap`.

- Library: `build_schedule(network, title, buffer_method="cap")`. The JSON exchange format
  accepts a top-level `"buffer_method"` key, which an explicit flag/argument overrides.
- The chosen method is recorded in `summary.md`, along with how many tasks in each protected
  chain had derived Δs; feeding and project buffers always use the same method within one
  schedule. A buffer is never smaller than 1 day. When a feeding chain cannot shift far enough
  to fit its full buffer, the achieved gap is all the protection that merge has — the summary
  shows `N (method wanted M)` so the shortfall is visible.
- Consumers: our-planner sets the method per project (`CCPM Method` in its project settings);
  the AI skill asks the user, and when the user is unsure it gathers two-point estimates
  and uses CAP.

- Whatever the method produces, buffers can be manually resized in our-planner before the
  project enters execution mode — the formula is a starting point, not a contract.

---

## Frequently Asked Questions (FAQ)

### How does `ccpm-scheduler` deal with feeding buffers when feeding chains are equally long as (or land tight against) the Critical Chain?

When a feeding chain finishes tight against its merge point on the Critical Chain (or when project start / resource constraints prevent shifting the feeding chain earlier), attempting to force a full-sized feeding buffer could risk elongating the Critical Chain or pushing project start before Day 0.

`ccpm-scheduler` resolves this using **constrained backward shifting**, **gap absorption (pre-consumed buffers)**, and **unprotected merge detection**:

1. **Constrained Backward Shifting**: The scheduler first attempts to shift the feeding chain backward to open up space for the calculated feeding buffer size $M$, bounded by Day 0, predecessor links, and resource availability across all chains.
2. **Pre-Consumed Buffers & Gap Absorption (`N (method wanted M)`)**: If the feeding chain cannot shift far enough to fit the full calculated buffer $M$, `ccpm-scheduler` fits whatever gap $N$ is available ($0 < N < M$). It sets the buffer duration to $N$ days without extending the Critical Chain, and reports `N (method wanted M)` in `summary.md` and CLI build stats so the buffer shortfall is fully visible.
3. **Unprotected Merges (`gap = 0`)**: If the feeding chain finishes tight against its critical successor ($N = 0$) and cannot shift earlier at all, `ccpm-scheduler` enforces a policy to **never emit a zero-length (0-day) buffer row**. The buffer is omitted entirely and flagged in `summary.md` with an explicit warning:
   > *"Warning: the merge ... has no room for a feeding buffer — that path is effectively critical. Watch it as closely as the critical chain."*

See the full [FAQ page](faq.md) for more answers to common scheduling and layout questions.

