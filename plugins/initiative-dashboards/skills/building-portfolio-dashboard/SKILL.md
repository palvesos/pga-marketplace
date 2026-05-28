---
name: building-portfolio-dashboard
description: >-
  Builds a self-contained HTML dashboard rolling up the status of
  multiple Jira initiatives or Value Milestones into a single executive
  view. For each initiative it drills down via the
  building-initiative-dashboard skill, generates the full per-initiative
  report, and surfaces the traffic-light, executive status bullets, and
  highlights/lowlights as a card in the rollup. Adds a portfolio-level
  KPI strip (RAG counts, total SP done/in flight/remaining, total open
  PRs). Stores per-portfolio state on disk so successive runs accumulate
  a time series of snapshots and surface a delta vs. the prior run. Use
  when the user asks to "build a portfolio dashboard for initiatives X,
  Y, Z", "rollup status for value milestone VM-123", "executive rollup
  for these initiatives", "VM status dashboard", or "summary across
  multiple initiatives".
allowed-tools: Bash(acli jira:*),Bash(gh search:*),Bash(gh pr:*),Bash(open:*),Bash(mkdir:*),Bash(ls:*),Bash(date:*)
---

# Building a Portfolio Dashboard

## When to Use

**Use this skill when the user asks to:**
- Roll up status across two or more Jira initiatives / epics into one view
- Build a dashboard for a Value Milestone that contains multiple
  initiative epics
- Produce an executive rollup for a portfolio of initiatives
- Summarise status across a list of Jira IDs (epics, VMs, or both)

**Do NOT use for:**
- Single-initiative reports → use `building-initiative-dashboard` directly
- Sprint or team-level status → that's a different shape of report
- Status of a single ticket → use `tooling-kit:jira`

## Prerequisites

1. The `building-initiative-dashboard` skill installed and working —
   this skill calls its workflow once per initiative
2. `acli` and `gh` authenticated (same as the inner skill)
3. The user provides **either**:
   - A comma-separated list of Jira keys (e.g. `RDUCH-151, RDUCH-169`)
   - A single Value Milestone key (e.g. `RPOR-28633`) — children are
     discovered automatically

## Workflow

### Step 0 — Confirm scope and prepare the portfolio folder

#### Step 0.0 — Required up-front questions

**Always ask, using `AskUserQuestion`, anything below that wasn't provided
in the activation prompt.** Do not silently default; do not start fetching
data until all answers are pinned.

1. **Portfolio input.** If the activation prompt didn't specify the input,
   ask whether the rollup is for a single **Value Milestone key** (e.g.
   `RPOR-28633`) or an **explicit list** of initiative keys (comma-separated
   Jira keys).

2. **Portfolio name (list-input only).** When the input is an explicit
   list of keys (no VM), ask the user for a short portfolio name — this
   becomes the slug used for the on-disk folder and filenames.
   Skip this question entirely when the input is a Value Milestone: the
   VM key drives the slug deterministically.

3. **Comparison window.** Ask which window the new portfolio snapshot
   should be compared against. Offer exactly two options:
   - *"Since last report"* (most recent prior portfolio snapshot) — recommended
   - *"Since last N weeks"* — and capture the N from the user

   **Skip this question only when no prior portfolio snapshot exists**
   for this slug (first run — nothing to compare against). In that case
   state *"first snapshot for this portfolio"* and proceed.

4. **Per-initiative state refresh scope.** Ask which child initiatives
   should also have their own per-initiative state snapshot refreshed
   as part of this portfolio run. Offer:
   - *"All initiatives"* — every child writes its own `.md` snapshot
   - *"None"* — only the portfolio-level `.md` is written; per-initiative
     dashboards are still generated for the rollup but their state
     folders are not touched (recommended for quick re-runs)
   - *"Named subset"* — capture the comma-separated list of Jira keys
     to refresh; all others render without writing per-initiative state

   The chosen scope drives the `write_state` flag passed to each
   per-initiative drill-down in Step 2.

These are hard requirements — the skill must not assume the input or
silently default to *"since last report"* / *"all initiatives"* when
prior snapshots exist.

#### Step 0.1 — Prepare the folder

Each portfolio gets its own folder on disk under a shared `portfolios/`
subdirectory so successive runs accumulate a time series of snapshots
that can be compared. Portfolio state lives **alongside** per-initiative
state to keep one root to manage.

**Base directory** (in order of precedence):
1. `$INITIATIVE_DASHBOARDS_DIR` environment variable, if set
2. `~/initiative-dashboards/` (default)

Portfolio state is rooted at `<base>/portfolios/<slug>/`.

**Portfolio slug** — derived as follows:

| Input kind        | Slug source                                                    |
|-------------------|----------------------------------------------------------------|
| Value Milestone   | The VM key, snake-cased + lowercased (e.g. `RPOR-28633` → `rpor_28633`) |
| Explicit list     | The portfolio name captured in Step 0.0.2, snake-cased + lowercased (e.g. *"Q2 Unification"* → `q2_unification`) |

Replace any character that isn't `[a-z0-9]` with `_`, then collapse
consecutive `_`.

**Timestamp** — `date +"%Y_%m_%d_%H_%M_%S"` (local time, sortable
lexicographically — same convention as the inner skill).

**Filenames** — both artifacts share the same stem:
- HTML: `<slug>__<timestamp>.html`
- State: `<slug>__<timestamp>.md`

```bash
BASE_DIR="${INITIATIVE_DASHBOARDS_DIR:-$HOME/initiative-dashboards}"
SLUG="rpor_28633"                              # derived from VM key or portfolio name
TS="$(date +"%Y_%m_%d_%H_%M_%S")"
FOLDER="$BASE_DIR/portfolios/$SLUG"
mkdir -p "$FOLDER"

# List prior portfolio state snapshots, newest first
ls -1t "$FOLDER"/*.md 2>/dev/null
```

#### Step 0.2 — Resolve the comparison target

Apply the window the user picked in Step 0.0.3 against the prior `.md`
files in `$FOLDER`. Exactly two windows are supported:

| User's answer                          | Resolution rule                                                |
|----------------------------------------|----------------------------------------------------------------|
| *"Since last report"*                  | Most recent `.md` file (top of `ls -1t`)                       |
| *"Since last <N> weeks"*               | Snapshot with the **latest timestamp on-or-before `N*7` days ago** |

**If the requested window pre-dates every stored snapshot** (oldest
`.md` newer than `today − N*7 days`):

1. Default to the **oldest available snapshot**.
2. Confirm with the user via `AskUserQuestion`, surfacing the gap, e.g.
   *"You asked for the last 6 weeks, but the oldest portfolio snapshot
   is from 3 weeks ago (2026-05-06). Compare against that instead?"*
3. If the user declines, treat the run as a first snapshot (no delta).

If there are **no prior snapshots at all**, skip the comparison and the
delta narrative — this is a first snapshot for this portfolio.

#### Step 0.3 — Load the chosen prior snapshot

Once a target file is selected, **read it via the Read tool** and keep
its frontmatter in working memory. It informs:
- the portfolio delta narrative (Step 4.5)
- the `previous_snapshot` field and `## Delta vs. previous snapshot`
  section in the new portfolio state file (Step 6)

If no prior snapshot exists, or the user declined the fallback in
Step 0.2, proceed without delta context and note *"First portfolio
snapshot"* in the user-facing report.

### Step 1 — Resolve the input to a list of initiative keys

If the input is a **single key**, detect whether it's a Value Milestone:

```bash
acli jira workitem view <KEY> --fields "summary,issuetype" --json
```

If `issuetype.name == "Value Milestone"`, walk down:

```bash
# Linked epics / children
acli jira workitem search --jql "\"Epic Link\" = <KEY> OR parent = <KEY> OR issue in linkedIssues(<KEY>)" \
  --fields "key,summary,issuetype" --csv
```

Filter to issuetypes `Epic` or `Initiative` — those are the initiative
roots. Skip Threat Models, HLDs, and other VM context items.

If the input is a **list**, use the keys verbatim.

**Always confirm the resolved initiative set with the user before
running the drill-down** — drill-downs are expensive (many Jira/PR
queries per initiative).

### Step 2 — Drill down per initiative

For each initiative key, follow the `building-initiative-dashboard`
workflow:

- Read the skill at
  `~/.claude/skills/building-initiative-dashboard/SKILL.md` (or the
  marketplace-installed path) and follow Steps 1–6
- Render the per-initiative dashboard to `$FOLDER/dashboard-<KEY>.html`
  (alongside the portfolio HTML, under the portfolio's folder from
  Step 0.1) — this is the inner skill's "output path override"
- **Pass `write_state` to the inner skill** based on the refresh scope
  the user chose in Step 0.0.4:
  - *"All initiatives"* → `write_state: true` for every drill-down
  - *"None"* → `write_state: false` (the default for output-path overrides)
  - *"Named subset"* → `write_state: true` only for keys in the subset;
    `false` for the rest

  When `write_state` is `true`, the inner skill also writes its own
  `<slug>__<timestamp>.md` under `$INITIATIVE_DASHBOARDS_DIR/<slug>/`
  and runs its own delta against the prior per-initiative snapshot —
  see the inner skill's Step 0.1 for the contract.
- **Capture** the following synthesised content from the per-initiative
  render — this populates the rollup card **and** the initiatives index
  table:
  - `key`, `title`, `productboard_url` (if any)
  - `rag_status` (`green` | `yellow` | `red`)
  - `rag_label`, `rag_headline`
  - `exec_status_bullets` (the 3-5 `<li>` bullets from the inner card 2)
  - `highlights[]`, `lowlights[]` (3 max each, the same bullets used in
    the inner card 3)
  - `sp_done`, `sp_in_flight`, `sp_remaining`, `sp_unsized_count`
  - `open_pr_count`
  - **`team`** — engineering team (Jira-project → team mapping, see
    inner skill's data-sources.md)
  - **`rpor_key`** / **`rpor_label`** — the parent RPOR (Value
    Milestone, Initiative, or Solution Enabler) for this epic.
    Discover via:
    ```bash
    # Try direct linkage first
    acli jira workitem search --jql "issue in linkedIssues(<KEY>) AND project = RPOR" \
      --fields "key,summary,issuetype" --csv
    # Fall back to summary-substring match if no direct link
    acli jira workitem search --jql "project = RPOR AND summary ~ \"<VM-keyword>\"" \
      --fields "key,summary,issuetype" --csv --limit 5
    ```
    `rpor_label` is a short tag like `PU-M2.1.8` (extract from the RPOR
    summary prefix).
  - **`target_start`**, **`target_due`**, **`ga_date`** — feed the
    portfolio Gantt chart. Resolution order:
    1. Read from the **parent RPOR** (preferred — that's where dates
       live for VMs, Initiatives, Solution Enablers):
       - `customfield_15485` — Target Start
       - `customfield_15486` — Target Due
       - `customfield_15491` — GA / EAP Date
    2. If the RPOR has no dates (e.g. an Initiative still in Definition),
       fall back to the **epic's own** dates:
       - `customfield_15330` — Target Start
       - `duedate` — Due Date
       - (no GA fallback at the epic level — leave `ga_date` null)

    Date values must be ISO `YYYY-MM-DD` strings. If any is missing,
    use `null`; the Gantt will skip the bar (or omit the GA marker)
    accordingly.

Do the drill-downs **sequentially** — the Jira CLI is rate-limited and
parallel calls can stomp on each other. A 5-initiative rollup typically
takes 2-4 minutes.

### Step 3 — Compute portfolio-level KPIs

Aggregate across all initiatives:

| KPI | How |
|---|---|
| Initiatives total | count of inputs |
| Green / Yellow / Red counts | count of `rag_status` per bucket |
| Total SP — Done | sum of `sp_done` |
| Total SP — In Flight | sum of `sp_in_flight` |
| Total SP — Remaining | sum of `sp_remaining` |
| Total Unsized items | sum of `sp_unsized_count` |
| Total open PRs | sum of `open_pr_count` |

### Step 4 — Draft the portfolio executive narrative

The portfolio header row has **two cards side-by-side**: the Executive
Status (left) and Highlights / Lowlights (right). Author both.

**Audience for both:** C-level + PM Leadership, same voice as the
per-initiative exec status (Engineering Director, synthetic, objective).

#### 4.1 Portfolio Executive Status

**Format:** 3-5 short `<li>` bullets, **hard cap 80 words total**.

**Content:**
- Overall portfolio posture in one bullet
- Cross-cutting wins or risks shared across multiple initiatives
- The single most important leadership-attention item

Same banned vocabulary applies (no `warrants attention`,
`encouraging`, etc.). No PR review-SLA noise. No Jira ticket keys.

#### 4.2 Portfolio Highlights / Lowlights

Same structure as per-initiative card 3:

- **Up to 3 highlights** (`<ul>` under `<h4>Highlights</h4>`) — the
  most important wins **across the portfolio**.
- **Up to 3 lowlights** (`<ul>` under `<h4>Lowlights</h4>`) — must
  be **actionable items** that leadership can help resolve:
  - **Blockers** (named team, named decision)
  - **Pending decisions** (named owners or alignment needed)
  - **Pending designs** (missing LLD / unscoped requirement)
  - **Cross-team dependencies** stalled

  **DO NOT** include passive observations ("Threat Model is unowned"
  is too soft → reframe to "Pending: assign Threat Model owner").
  Each lowlight should imply *who acts and what they decide*.

**Bullet format — code chip + friendly name (portfolio H/L only).**
Each bullet in the portfolio Highlights/Lowlights must:

1. Start with a small **initiative code chip** linking to Jira. Use
   `<a class="li-key" href="https://outsystemsrd.atlassian.net/browse/<KEY>" target="_blank">KEY</a>`
2. Reference the initiative by its **friendly name in bold**
   (`<strong>…</strong>`) — never by its Jira key or the PU-Mx code.
   Use the initiative's `title_short` (or a shorter readable form).

Example:
```html
<li><a class="li-key" href="…/browse/RDUCH-169" target="_blank">RDUCH-169</a>
    First production code shipped on <strong>LT Connectivity</strong>
    (RQ01 M1 merged)</li>
```

This pattern gives scannability via the leading chip while keeping the
bullet readable as natural prose. The same pattern applies to both
Highlights and Lowlights.

If a bullet truly spans multiple initiatives (rare), reframe it to be
specific to one — or chain 2-3 chips before the text.

Wrap each section in `<div class="hl-section highlights">` /
`<div class="hl-section lowlights">` so the badge CSS picks up.

PR review-SLA noise rule still applies — no `idle in review` etc.

### Step 4.5 — Compute the portfolio delta vs. previous snapshot

Skip this step on the first portfolio snapshot.

Using the frontmatter loaded in Step 0.3, compute the following deltas
against the prior portfolio snapshot. The result feeds both the
*Delta vs. previous snapshot* section of the new `.md` (Step 6) and a
one-line callout in the user-facing report (Step 7).

| Delta            | How                                                              |
|------------------|------------------------------------------------------------------|
| Initiatives added   | keys in new set, not in prior set                            |
| Initiatives removed | keys in prior set, not in new set                            |
| RAG transitions     | per-key `rag_status` changes (e.g. *RDUCH-169: Yellow → Green*) |
| SP shifts           | KPI deltas: `sp_done`, `sp_in_flight`, `sp_remaining`, `sp_unsized_count` |
| Open-PR shift       | `open_pr_count` delta                                        |
| Headline change     | which initiative drove the biggest RAG severity move         |

If the input was a Value Milestone and Step 1 re-walked the VM children,
the *Initiatives added/removed* deltas naturally capture VM scope
changes between runs.

### Step 5 — Render the portfolio dashboard

1. Read the template at
   [reference/portfolio-template.html](reference/portfolio-template.html)
2. Substitute the placeholders:
   - `{{PORTFOLIO_TITLE}}` — e.g. "Q2 Initiatives Portfolio" or the VM
     name if the input was a VM
   - `{{PORTFOLIO_SUBTITLE}}` — e.g. "Status of N initiatives ·
     YYYY-MM-DD" plus the input echo (VM key or comma-separated keys)
   - `{{KPI_*}}` — the seven KPI values from Step 3
   - `{{INITIATIVES_INDEX_JSON}}` — JSON array driving the filterable
     **Initiatives Index** table **and** the click-to-show detail panel.
     One object per initiative:
     ```json
     {
       "key": "RDUCH-169",
       "title_short": "PU-M4.13.1 LT Connectivity",
       "rag_status": "green",
       "rag_label": "Green",
       "rag_headline": "Both LLDs approved and first RQ01 milestone shipped.",
       "team": "Unification Charlie",
       "rpor_key": "RPOR-28605",
       "rpor_label": "PU-M4.13",
       "exec_html": "<ul>…</ul>",
       "hl_html": "<div class='hl-section highlights'>…</div><div class='hl-section lowlights'>…</div>"
     }
     ```
     The table renders Initiative key, title (linked to the
     per-initiative dashboard), RAG pill, owner team, and parent RPOR.
     Filters at the top narrow by **Owner Team** and **Parent RPOR**.
     **Clicking any row** highlights it and renders that initiative's
     RAG light + Executive Status + Highlights/Lowlights into the
     "Selected initiative" detail panel directly below the table.
     The detail panel defaults to the highest-severity row visible.
   - `{{PORTFOLIO_EXEC_HTML}}` — the `<ul>...</ul>` from Step 4.1
   - `{{PORTFOLIO_HL_HTML}}` — the two `<div class="hl-section …">`
     blocks (Highlights + Lowlights) from Step 4.2
   - `{{SNAPSHOT_DATE}}` — today's date
   - `{{SOURCES_LINE}}` — which sources were queried per initiative
3. Write to `$FOLDER/<slug>__<timestamp>.html` (path from Step 0.1).
   **Append-only** — never overwrite or delete prior HTML or `.md` files
   in `$FOLDER`. The timestamped filename makes collisions impossible at
   second-level resolution.
4. Write the state snapshot to `$FOLDER/<slug>__<timestamp>.md` — see
   **Step 6** for the schema.
5. Open it: `open $FOLDER/<slug>__<timestamp>.html`

#### Detail-panel data shape

The detail panel below the index table is **fully data-driven** from
`{{INITIATIVES_INDEX_JSON}}`. For each initiative, pass:

- `exec_html` — the same `<ul>` of 3-5 `<li>` bullets used in the
  per-initiative dashboard's hero "Executive Status" card
- `hl_html` — the two `<div class="hl-section …">` blocks
  (Highlights + Lowlights) used in the per-initiative dashboard's
  hero "Highlights / Lowlights" card

The skill is responsible for capturing these from the per-initiative
render in Step 2 and bundling them per initiative.

The detail panel always links to `dashboard-<KEY>.html` for the
currently-selected initiative — that's the drill-down path.

### Step 6 — Write the portfolio state snapshot (`.md`)

Write a markdown file alongside the HTML using YAML frontmatter for
machine-readable values and a brief narrative body. This file is what
future portfolio runs read to compute deltas, and what the user can
grep / open directly.

**Schema:**

```markdown
---
portfolio_slug: rpor_28633
portfolio_title: PU-M4.13 — Unification Connectivity VM
input_kind: value_milestone                  # value_milestone | list
input_keys: [RPOR-28633]                     # raw user input (VM key or comma-separated keys)
resolved_initiative_keys: [RDUCH-169, RDUCH-151, RDUCH-200]
snapshot_iso: 2026-05-28T09:14:02Z
snapshot_date: 2026-05-28
html_file: rpor_28633__2026_05_28_09_14_02.html
previous_snapshot: rpor_28633__2026_05_14_08_02_11.md   # or null on first run
refresh_scope: subset                        # all | none | subset
refreshed_keys: [RDUCH-169]                  # keys for which write_state=true was passed (omit when refresh_scope=all/none)
kpis:
  initiatives_total: 3
  rag_green: 1
  rag_yellow: 1
  rag_red: 1
  sp_done: 142
  sp_in_flight: 64
  sp_remaining: 88
  sp_unsized_count: 14
  open_pr_count: 27
initiatives:
  - key: RDUCH-169
    title_short: PU-M4.13.1 LT Connectivity
    rag_status: green
    rag_label: Green
    rag_headline: Both LLDs approved and first RQ01 milestone shipped.
    team: Unification Charlie
    rpor_key: RPOR-28605
    rpor_label: PU-M4.13
    sp_done: 67
    sp_in_flight: 32
    sp_remaining: 31
    sp_unsized_count: 8
    open_pr_count: 12
    target_start: 2026-03-01
    target_due: 2026-08-15
    ga_date: 2026-09-30
    per_initiative_html: dashboard-RDUCH-169.html    # path relative to $FOLDER
    per_initiative_state: rduch_169__2026_05_28_09_14_02.md    # null if write_state was false this run
sources_queried: [Jira, GitHub]
---

# Portfolio snapshot — 2026-05-28

## Portfolio Executive Status
- <bullet 1>
- <bullet 2>
- <bullet 3>

## Highlights
- <…>

## Lowlights
- <…>

## Delta vs. previous snapshot (2026-05-14)
- Initiatives added: <none | KEY,…>
- Initiatives removed: <none | KEY,…>
- RAG transitions:
  - RDUCH-169: Yellow → Green
  - RDUCH-200: Green → Yellow
- SP shifts: Done +12, In Flight −4, Remaining −8
- Open PRs: 31 → 27 (−4)
- Headline change: RDUCH-200 slipped from Green to Yellow — Threat Model
  still unowned past the LLD checkpoint.

<!-- omit the "Delta" section entirely if previous_snapshot is null -->
```

**Rules:**

- The frontmatter is the canonical machine-readable state; the
  narrative body is the same content surfaced in the HTML's portfolio
  exec card + highlights/lowlights card.
- The `initiatives` list must include **every** key in the rollup, in
  the same order they appear in the dashboard's Initiatives Index
  (sorted Red → Yellow → Green, alphabetical within colour).
- Each initiative entry must include `key`, `title_short`, `rag_status`,
  `team`, `rpor_key`, `sp_done`, `sp_in_flight`, `sp_remaining`,
  `open_pr_count`, and `per_initiative_html`. Missing fields force the
  next run to re-derive them.
- Record `refresh_scope` and `refreshed_keys` so the next run can audit
  which children had their own state refreshed.
- Do not write secrets or PII beyond what's already in the HTML.

### Step 7 — Report back to the user

Tell the user:
- the absolute paths to both the portfolio HTML and `.md`
- the comparison target used — either the resolved prior snapshot
  (e.g. *"compared against rpor_28633__2026_05_14_08_02_11.md
  (14 days ago, matched your 'last 2 weeks' request)"*) or
  *"first portfolio snapshot"* if none was available
- the refresh scope applied and, when *"subset"*, the keys refreshed
- a one-line headline of the portfolio delta (e.g.
  *"RAG steady at 1G/1Y/1R; SP Done +12 since 2026-05-14"*) — omit
  on first snapshot

## Best Practices

1. **Confirm the resolved initiative set before drilling down.** A
   wrong VM walk can produce a 10-minute run against irrelevant tickets.
2. **Reuse the inner skill's hero output verbatim.** Don't re-derive
   RAG or rewrite the exec bullets — the per-initiative dashboard is
   already canonical; just copy.
3. **Sort initiative cards by RAG severity** (Red first, then Yellow,
   then Green). Leadership scanning starts at the worst.
4. **Keep the portfolio exec summary at ≤80 words.** It's a higher
   layer of abstraction; don't repeat per-initiative detail.
5. **Generate the per-initiative dashboards before the rollup HTML.**
   The rollup links to them; broken links read as sloppy.
6. **Snapshots are append-only** — never overwrite or delete prior
   `.md` or `.html` files in `$FOLDER`. Each run adds a new timestamped
   pair so the user can scroll back through portfolio history.
7. **Mind the refresh scope.** *"All"* is expensive on large VMs (one
   inner state walk per child); *"None"* is the fast default for
   quick re-runs. *"Subset"* is the right call when only a couple of
   initiatives moved.

## Common Mistakes

### ❌ Parallelising the drill-downs
Jira CLI gets noisy with concurrent calls.
→ **Always sequential.**

### ❌ Duplicating the exec text in the portfolio summary
The cards already show per-initiative exec bullets.
→ **The portfolio exec summary is cross-cutting; don't repeat.**

### ❌ Rendering with stale RAG values
If you cache and the inner skill is updated, RAG can drift.
→ **Re-run the inner workflow each time. Don't read prior dashboards
back as source of truth.**

### ❌ Forgetting to sort by severity
A green-first ordering buries the lead.
→ **Red, then Yellow, then Green. Within a colour, alphabetical by key.**

### ❌ Overwriting the portfolio HTML on re-run
Single-file `portfolio-dashboard.html` writes destroy history.
→ **Always write to `$FOLDER/<slug>__<timestamp>.html` (+ `.md`) so
snapshots accumulate.**

### ❌ Refreshing every child by default
*"All initiatives"* on a large VM can take 10+ minutes.
→ **Ask the user explicitly via Step 0.0.4; default expectation is
*"None"* for quick re-runs.**

## Quick Reference

| Step | Command |
|---|---|
| Detect VM | `acli jira workitem view <KEY> --fields "issuetype" --json` |
| Find VM children (epics) | `acli jira workitem search --jql "\"Epic Link\" = <VM> OR parent = <VM> OR issue in linkedIssues(<VM>)"` |
| Per-initiative drilldown | Follow `building-initiative-dashboard` SKILL.md (pass `write_state` per Step 0.0.4) |
| Compute timestamp | `date +"%Y_%m_%d_%H_%M_%S"` |
| Create portfolio folder | `mkdir -p "${INITIATIVE_DASHBOARDS_DIR:-$HOME/initiative-dashboards}/portfolios/<slug>"` |
| List prior portfolio snapshots | `ls -1t <folder>/*.md \| head -5` |
| Render | Substitute template placeholders, write `$FOLDER/<slug>__<timestamp>.html` + `.md` |
| Open | `open <path>` |

## Reference Files

| File | Purpose |
|---|---|
| [reference/portfolio-template.html](reference/portfolio-template.html) | The portfolio HTML template with placeholders |

The inner skill (`building-initiative-dashboard`) provides:
- `reference/data-sources.md` — per-initiative data source commands
- `reference/dashboard-template.html` — per-initiative HTML template
