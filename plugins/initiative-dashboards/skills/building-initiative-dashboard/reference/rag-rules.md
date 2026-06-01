# RAG Status Rules

Shared rubric used by both `building-initiative-dashboard` (which
authors the RAG) and `building-portfolio-dashboard` (which rolls it
up). Keep the two in lockstep by using the inputs, labels, and
vocabulary defined here.

This is a **soft rubric** — the author picks the colour, but the call
must be grounded in at least one of the inputs below, and the headline
must name which one drove it. The point isn't to remove judgement; it
is to remove "Yellow because vibes" and to make per-track and
cross-initiative comparisons meaningful.

## Where this applies

| Skill                           | Where the rule lands                                                              |
|---------------------------------|-----------------------------------------------------------------------------------|
| `building-initiative-dashboard` | Step 5.1 hero card 1 (overall RAG) **and** Step 5.2 per-track RAG in the Progress Summary |
| `building-portfolio-dashboard`  | Step 2 — reuse per-initiative RAG verbatim; never recompute or override            |

## Labels (canonical set)

Pick the colour first using the inputs below, then the label.

| `rag_status` | Canonical `rag_label` | When to use                                                                                                |
|--------------|-----------------------|------------------------------------------------------------------------------------------------------------|
| `green`      | `On Track`            | Scope, schedule, and design are all healthy.                                                               |
| `yellow`     | `At Risk`             | One input is degraded but the initiative is still recoverable without escalation.                          |
| `red`        | `Off Track`           | Multiple inputs are degraded, or one is severe and unrecoverable without leadership help.                  |

`Pre-implementation` is a **label modifier**, not a status. Use it as
the `rag_label` (in place of `On Track` / `At Risk` / `Off Track`) when
the initiative has not entered the build phase yet — design is still
in flight, no implementation stories have started. Its colour follows
the rubric like any other state:

- **Green + `Pre-implementation`** — design is on schedule, nothing
  expected to be in flight yet (e.g. brand-new initiative still inside
  its design window).
- **Yellow + `Pre-implementation`** — implementation was expected to
  have started by now but hasn't (design is overrunning, or the
  implementation epic is still In Design past its planned start).
- **Red + `Pre-implementation`** — design has stalled with no path to
  start implementation in the current window.

Rules:
- `rag_status` is always lowercase: `green` | `yellow` | `red`.
- Use the canonical labels above. Don't invent variants
  (`On Track w/ caveats`, `Mostly Green`).
- One label per initiative and one per track. No half-colours.

## Inputs (the six signals)

The author must name at least one of these in the headline. The
Progress Summary should reference the same input when it justifies
the per-track RAGs.

1. **Scope progress.** % of sized SP delivered against the expected
   burndown at this point in the window. Meaningfully behind → Yellow.
   A track stalled with no in-flight work → Red.
2. **Schedule risk.** Time remaining to `target_due` vs. work remaining
   (sized SP + a reasonable estimate for unsized items). Remaining
   work doesn't plausibly fit → Yellow. Can't fit even with
   re-prioritisation → Red.
3. **Sequencing.** Implementation stories started before the matching
   LLD / design is approved → at minimum Yellow. Multiple tracks
   doing this → Red.
4. **Unsized scope.** A material slice of the work isn't sized
   (rough guide: ≥ 20% of items unsized) → at minimum Yellow. The SP
   rollup is no longer trustworthy and the headline must say so.
5. **Dependencies.** Cross-team work the initiative depends on that
   is itself Yellow/Red, or has no committed delivery date, drags the
   initiative one step worse than it would otherwise be.
6. **Open decisions / design gaps.** Outstanding decisions blocking
   the next milestone, or missing LLDs for work scheduled this
   window → Yellow. If they block the critical path → Red.

**Worst-of, not average.** Two Green inputs and one Red input is a Red
overall. The point of the colour is to surface the worst signal, not
to smear it across the average.

## Headline (one sentence, mandatory)

Every RAG — overall and per-track — needs **one factual sentence** that
names the dominant input. The headline is what an EM repeats in a
meeting; if it can't be repeated, rewrite it.

Headline rules:
- One sentence, **≤ 25 words**.
- Names the input that drove the colour (scope / schedule /
  sequencing / unsized / dependency / design gap).
- No PR review SLA observations ("PRs idle in review for >24h"). PR
  hygiene belongs in the Progress Summary, not in the RAG signal.
- No editorial vocabulary ("warrants attention", "encouraging
  progress", "concerning"). The colour is the editorial signal.
- No Jira ticket keys in the overall headline — name the track or
  the team. (Per-track headlines may reference the blocking story
  key when it is *the* blocker.)

Examples:
- ✅ *"At Risk — RQ02 LLD review outstanding past planned start."*
- ✅ *"Off Track — Threat Model unowned; blocks two dependent tracks."*
- ✅ *"On Track — 67/145 SP delivered, both LLDs approved, no open blockers."*
- ❌ *"Yellow — some concerns."* (no input named)
- ❌ *"Yellow because vibes."* (banned)
- ❌ *"At Risk — encouraging progress but PRs are idle in review."* (editorial + PR-SLA)

## Per-track RAG

Same rubric, scoped to a single track. A track's RAG can be Green
when the overall is Yellow — that's why we break it out. The
per-track headline appears next to the colour in the Progress
Summary; same one-sentence, input-named rule applies.

## Portfolio rollup

The portfolio skill **reuses per-initiative RAG verbatim**. It does
not recompute, average, or override.

- Counts (`rag_green`, `rag_yellow`, `rag_red`) drive the KPI strip.
- Initiative cards are sorted Red → Yellow → Green (alphabetical
  within colour) so leadership scans the worst first.
- The portfolio dashboard intentionally does **not** produce a single
  overall portfolio RAG light. The G/Y/R count strip carries the
  signal; collapsing a portfolio of disparate initiatives into one
  colour hides more than it reveals.

### Stale snapshots

If a per-initiative snapshot is older than **14 days** at portfolio
snapshot time, tag it as `stale` in the index table but **do not**
change its RAG. The author of the next per-initiative refresh owns
the colour. Surfacing staleness in the table lets leadership ask
"why hasn't this moved?" without hiding the underlying signal.

## Cross-skill consistency checklist

When updating either skill, keep the following in lockstep:

- The label vocabulary (`On Track` / `At Risk` / `Off Track` /
  `Pre-implementation`).
- The lowercase status values (`green` | `yellow` | `red`).
- The headline format and word cap.
- The banned vocabulary list (no PR-SLA noise, no editorial filler).
- The "worst-of, not average" rule.

If you change any of those, change them here first, then update
both SKILL.md files to match.
