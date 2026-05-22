---
name: building-sprint-review
description: >-
  Builds a Scrum Sprint Review package from a Jira sprint — a Markdown report
  (for async distribution via Slack/Confluence/email) and a self-contained
  HTML slide deck (for the live Sprint Review meeting). The package covers
  sprint goal vs. outcome, committed vs. completed Story Points, velocity vs.
  rolling average, completed stories with demo notes, carryover with reasons,
  bugs and scope changes, and next-sprint preview. Use when the user asks to
  "build a sprint review for RDUCH Sprint 24", "prepare the sprint review
  deck for sprint 12345", "generate sprint review report for <sprint>",
  "make slides for tomorrow's sprint review of <sprint>", or "wrap up
  sprint <X> with a review presentation and report".
allowed-tools: Bash(acli jira:*),Bash(gh search:*),Bash(gh pr:*),Bash(npx:*),Bash(open:*),Bash(mkdir:*),Bash(ls:*),Bash(date:*)
---

# Building a Sprint Review (Presentation + Report)

## When to Use

**Use this skill when the user asks to:**
- Build a sprint review presentation, deck, slides, or report for a Jira sprint
- Wrap up a sprint with a review package for stakeholders
- Generate the artifact a Scrum Master / EM presents at the Sprint Review ceremony
- Summarise what was delivered, what slipped, and what's next, scoped to one sprint

**Do NOT use for:**
- Initiative / epic progress across many sprints → use `building-initiative-dashboard`
- Portfolio rollups across initiatives → use `building-portfolio-dashboard`
- Retrospective notes (process, people) → out of scope; this is the *Review*, not *Retro*
- Single-ticket status → use `tooling-kit:jira` directly

## Prerequisites

1. `acli` authenticated against Atlassian (`acli jira auth status`)
2. `gh` authenticated against GitHub (`gh auth status`) — optional, only used
   to surface merged PRs alongside Done stories
3. An **explicit sprint identifier** from the user — either:
   - A sprint **name** (e.g. `"RDUCH Sprint 24"`, `"Unification Charlie - Sprint 24"`)
   - A sprint **numeric ID** (e.g. `12345`)
   - Or the keyword `last` resolved against a specific project (e.g. `last sprint of RDUCH`)
     → resolve via `sprint in closedSprints() AND project = <PROJ> ORDER BY endDate DESC` and take the first one
4. The Jira project key (defaults to `RDUCH` when the user is talking about Unification Charlie)

**Do not default to an active sprint silently.** If the user has not given a
sprint identifier, ask which sprint — by name or ID — before proceeding.

## Workflow

### Step 1 — Resolve the sprint

Take the sprint identifier the user gave you and run:

```bash
# By name
acli jira workitem search \
  --jql 'sprint = "RDUCH Sprint 24"' \
  --fields "key,summary,status,assignee,issuetype,priority,labels" \
  --csv --limit 200

# By numeric ID
acli jira workitem search \
  --jql 'sprint = 12345' \
  --fields "key,summary,status,assignee,issuetype,priority,labels" \
  --csv --limit 200
```

Then pull one ticket in full JSON to extract the **sprint metadata** embedded
in the Sprint custom field:

```bash
acli jira workitem view <ANY-KEY-FROM-RESULTS> --fields '*all' --json \
  | jq '.fields.customfield_10006 // .fields.sprint // empty'
```

The Sprint field is an array of sprint blobs containing `id`, `name`,
`state` (`active`/`closed`/`future`), `startDate`, `endDate`, `goal`, and
`boardId`. Use this to populate the sprint header (name, dates, goal) in
both artifacts.

If the field ID `customfield_10006` isn't populated for your instance, fall
back to `.fields.sprint` or grep the raw output for `com.atlassian.greenhopper`.
See **[reference/data-sources.md](reference/data-sources.md)** for full
details on the sprint blob format and OutSystems-specific field IDs.

### Step 2 — Pull the ticket detail you need

For every ticket in the sprint, capture:

- `key`, `summary`, `status.name`, `assignee.displayName` (or emailAddress),
  `issuetype.name`, `priority.name`, `labels[]`
- **Story Points** from `customfield_10004`
- **Parent Epic** — request `parent` and `customfield_10007` (Epic Link) so
  Done items can be grouped by epic on the "What we shipped" slide. The
  search query MUST include these fields explicitly:

  ```
  fields: ["summary","status","assignee","issuetype","priority","labels",
           "customfield_10004","customfield_10007","parent",
           "customfield_10006","customfield_12600","resolutiondate","created"]
  ```

  For each ticket, extract `parent.key` + `parent.fields.summary` (or fall
  back to `customfield_10007` if `parent` is not set on the issue type).
  Tickets with no parent get grouped under `(No epic)`.
- **Original commitment flag** — did the ticket start in the sprint or get
  added mid-sprint? Use the Sprint field history (`changelog`) to detect
  added/removed mid-sprint.
- **Resolution date** — for Done tickets, when they moved to Done
- **PR linkage** from `customfield_12600` (regex `state=([A-Z]+)`,
  `stateCount=(\d+)`), then resolve the URL via `gh search prs "<KEY>"`

Pull the changelog with:

```bash
acli jira workitem view <KEY> --fields '*all' --expand changelog --json
```

Two analyses depend on this changelog:

1. **Mid-sprint scope detection** — `changelog.histories[].items[]` where
   `field == "Sprint"` shows which sprint(s) the ticket moved in/out of,
   with timestamps. A ticket **added mid-sprint** is one whose Sprint
   field was set to the current sprint *after* the sprint's `startDate`.
   Mark it `added_mid_sprint: true` so the report can break out "scope
   changes".
2. **Phase-time metrics** — `histories[].items[]` where `field == "status"`
   gives the full status-transition timeline. Build an ordered list of
   `{at: history.created, from: fromString, to: toString}` per Done item.
   This feeds the Ticket KPIs table on slide 3 (avg days In Progress / In
   Review / In Testing per epic) — see Step 7. Without changelog the
   table degrades to an empty-state line.

For 10–20 Done items, pulling the changelog per-item via
`getJiraIssue --expand changelog` is the only reliable path — the
search-API does not expose changelog in the slim view. Delegate the
batch pull to a subagent if you want to keep the main context clean.

### Step 3 — Compute the metrics

Build these numbers from the ticket set:

| Metric | Definition |
|---|---|
| **Committed SP** | Sum of SP across tickets that were in the sprint at `startDate` (i.e. not `added_mid_sprint`). Unsized = 0. |
| **Completed SP** | Sum of SP across tickets currently in `Done` status. |
| **Carryover SP** | Sum of SP across tickets not in `Done` (will roll to next sprint). |
| **Scope-added SP** | Sum of SP across `added_mid_sprint` tickets, broken into Done vs. not-Done. |
| **Velocity** | `Completed SP` for this sprint. |
| **Avg velocity (last 3)** | Average of `Completed SP` across the 3 most recently closed sprints of this board / project. |
| **Bugs found in sprint** | Count of `issuetype = Bug` tickets created during sprint window. |
| **Unsized count** | Tickets in the sprint with `sp == null` and `issuetype != Epic`. |

**Average velocity query** (run once, after sprint resolution):

```bash
# Last 3 closed sprints of the same board (or same project, if board unknown)
acli jira workitem search \
  --jql 'sprint in closedSprints() AND project = RDUCH AND status = Done' \
  --fields "key,customfield_10004,customfield_10006" \
  --csv --limit 500
```

Then group by sprint name, sum SP per sprint, and average the 3 most recent
(excluding the current sprint). If fewer than 3 closed sprints exist for the
project, report `avg velocity = n/a (only X prior sprints available)` rather
than averaging a tiny sample.

### Step 4 — Classify completion buckets

For each ticket assign one of these completion buckets — they drive both
the report tables and the deck slides:

| Bucket | Predicate |
|---|---|
| **Committed & Done** | Was in sprint at start AND status = Done |
| **Committed & Carryover** | Was in sprint at start AND status ≠ Done |
| **Added & Done** | Added mid-sprint AND status = Done |
| **Added & Carryover** | Added mid-sprint AND status ≠ Done |
| **Removed** | Was in sprint at start, later moved out (changelog shows Sprint field cleared/changed mid-sprint) |

`Committed & Done` is the only "clean win" bucket. `Added & Done` is good
but should be flagged as scope change. `Committed & Carryover` is the
honest slip. Show all five buckets in the report — don't roll them up
prematurely.

### Step 5 — Pull team context (optional, recommended)

Two team-specific sources to enrich the artifacts:

**Confluence team page** — for the Unification Charlie team this is:
`https://outsystemsrd.atlassian.net/wiki/spaces/RDO11PC/pages/5852397579/Unification+Charlie+Team`

```bash
# Page ID 5852397579 — pulls team roster, working agreements, sprint cadence
koda tool confluence get --page-id 5852397579
```

Use the team page to populate:
- Team name on the title slide / report header
- Team roster (for the "demo owners" suggestion list — match assignees against members)
- Sprint cadence / working agreement notes (cite in the footer if relevant)

If the user names a different team, ask them for the Confluence page ID
rather than guessing.

**Slack channel** — `#unification-charlie` at
`https://outsystems.enterprise.slack.com/archives/C0ABRM13LLS`. The skill
**does not post** to Slack automatically — the user shares the artifacts
themselves. Include the channel URL in the report footer and on the final
deck slide so the audience knows where follow-up discussion happens.

If credentials are missing for Confluence, **skip it gracefully**: produce
the artifacts with the sprint name only on the title slide, no roster.

### Step 6 — Render the Markdown report

Read [reference/report-template.md](reference/report-template.md) and
substitute:

| Placeholder | Source |
|---|---|
| `{{SPRINT_NAME}}` | Sprint field `name` |
| `{{SPRINT_GOAL}}` | Sprint field `goal` (or "No goal recorded in Jira" if blank) |
| `{{SPRINT_DATES}}` | `startDate` → `endDate`, formatted `YYYY-MM-DD → YYYY-MM-DD` |
| `{{TEAM_NAME}}` | From Confluence team page, or default `Unification Charlie` for RDUCH |
| `{{COMMITTED_SP}}` / `{{COMPLETED_SP}}` / `{{CARRYOVER_SP}}` | Step 3 metrics |
| `{{COMPLETION_PCT}}` | `Completed SP / Committed SP * 100`, rounded; `n/a` if Committed = 0 |
| `{{VELOCITY}}` / `{{AVG_VELOCITY}}` | Step 3 metrics |
| `{{BUGS_FOUND}}` / `{{SCOPE_ADDED_SP}}` / `{{UNSIZED_COUNT}}` | Step 3 metrics |
| `{{GOAL_OUTCOME}}` | One of `Achieved` / `Partially achieved` / `Not achieved` / `No goal` — your call based on metrics + carryover |
| `{{GOAL_OUTCOME_REASON}}` | One sentence justifying the verdict (e.g. "All committed stories shipped; one bug found post-deploy.") |
| `{{SAFE_SPRINT_NAME}}` | Sprint name lowercased, spaces → `-`, non-alphanumeric stripped — used both in filenames and in the report's "Live deck" reference |
| `{{COMMITTED_DONE_TABLE}}` | Markdown table: Key, Summary, SP, Assignee, PR (if any) |
| `{{ADDED_DONE_TABLE}}` | Same shape, only `added_mid_sprint` & Done |
| `{{CARRYOVER_TABLE}}` | Same shape + a "Reason" column you fill with one short phrase per ticket (blocked / unfinished / re-scoped / etc.) |
| `{{REMOVED_TABLE}}` | Only present if there were any; otherwise omit the whole section |
| `{{BUGS_SECTION}}` | Short bulleted list of bugs found, with key + summary |
| `{{NEXT_SPRINT_PREVIEW}}` | If the next sprint exists (state=`future` on same board) and has tickets, list the top items by priority. Otherwise: "Next sprint not yet planned." |
| `{{SLACK_URL}}` / `{{CONFLUENCE_URL}}` | Team links — defaults below for Unification Charlie |
| `{{SNAPSHOT_DATE}}` | Today's date, `YYYY-MM-DD` |

**Defaults for Unification Charlie / RDUCH:**
- Slack: `https://outsystems.enterprise.slack.com/archives/C0ABRM13LLS`
- Confluence: `https://outsystemsrd.atlassian.net/wiki/spaces/RDO11PC/pages/5852397579/Unification+Charlie+Team`

Write to `<CWD>/sprint-review-<SAFE_SPRINT_NAME>.md`. `SAFE_SPRINT_NAME` is
the sprint name lowercased, with spaces → `-` and any non-alphanumeric
stripped (e.g. `RDUCH Sprint 24` → `rduch-sprint-24`).

### Step 7 — Render the HTML deck

Read [reference/presentation-template.html](reference/presentation-template.html)
and substitute the same placeholders plus a few deck-specific ones:

| Placeholder | Source |
|---|---|
| `{{DECK_TITLE}}` | `{{TEAM_NAME}} — {{SPRINT_NAME}} Review` |
| `{{SPRINT_GOAL_SHORT}}` | Sprint goal in ≤80 characters (truncate with ellipsis if needed) — used as the slide-2 headline |
| `{{GOAL_OUTCOME_CLASS}}` | One of `achieved` / `partial` / `missed` / `nogoal` (lowercase, drives the banner colour) |
| `{{GOAL_OUTCOME_REASON}}` | One sentence justifying the outcome verdict |
| `{{DEMO_SLIDES_HTML}}` | One `<section class="slide demo-slide">` per `Committed & Done` story (then `Added & Done`). See the inline demo-slide markup below. |
| `{{COMMITTED_DONE_LIST_HTML}}` | **Grouped by parent Epic.** One outer `<li class="epic-group">` per epic, ordered by total SP descending. Each contains an epic header + a nested `<ul>` of the items in that epic. See the "Delivered-list epic grouping" structure below. |
| `{{SCOPE_CHANGES_HTML}}` | Three small sections: Added & Done, Added & Carryover, Removed. If all three empty: render `<div class="empty-state">No scope changes this sprint.</div>` |
| `{{CARRYOVER_LIST_HTML}}` | `<li>` rows like the delivered list, plus an `<span class="item-reason">…</span>` with the one-phrase reason. Empty-state line if nothing carried over. |
| `{{NEXT_SPRINT_HTML}}` | `<li>` rows for the next-sprint preview. Empty-state line if no future sprint. |
| `{{COMMITTED_DONE_SP}}` / `{{ADDED_DONE_SP}}` | Raw numbers (SP) for the doughnut chart on slide 4 |
| `{{BURNDOWN_JSON}}` | Optional — see Step 7b. Pass `null` (literal, no quotes) to skip the burndown line chart; the template will fall back to the velocity-history bar instead. |
| `{{VELOCITY_HISTORY_JSON}}` | Array `[{name, sp, current}]` for prior closed sprints + this one (`current:true` on the most recent). Pass `[]` to hide the fallback too. |
| `{{KPI_BUCKETS_JSON}}` | Object keyed by bucket name; powers the click-to-drill table on the "By the numbers" slide. See **KPI bucket payload** below. Pass `{}` and the cards will render empty drilldowns. |
| `{{SPRINT_HISTORY_HTML}}` | A `<table>` rendered on the Trends slide below the charts. Columns: Sprint · Capacity · Velocity · Overflow · Scope Δ · Delivery%. One row per sprint, newest first, current sprint marked with `class="current"`. See **Sprint history table** below. |
| `{{TICKET_KPIS_HTML}}` | A `<table>` rendered on the "By the numbers" slide below the KPI grid. One row per epic that has at least one Done item this sprint, plus a final sprint-average row (`class="epic-total"`). Columns: Epic · Done · In Progress · In Review · In Testing · PR Cycle · Lead Time. All time columns are average **days** across Done items in that epic. See **Ticket KPIs table** below. |

**Sprint history table** (the `{{SPRINT_HISTORY_HTML}}` placeholder):

```html
<table>
  <thead><tr>
    <th>Sprint</th>
    <th>Capacity</th>
    <th>Velocity</th>
    <th>Overflow</th>
    <th>Scope Δ</th>
    <th>Delivery%</th>
  </tr></thead>
  <tbody>
    <tr class="current">
      <td>RDUCH 26.Q2.4</td>
      <td>96</td><td>50</td><td>46</td><td>+2</td>
      <td class="delivered-mid">52%</td>
    </tr>
    <tr>
      <td>RDUCH 26.Q2.3</td>
      <td>40</td><td>33</td><td>7</td><td>+5</td>
      <td class="delivered-high">82%</td>
    </tr>
    …
  </tbody>
</table>
```

**Per-sprint metrics** (compute for the current sprint + the last 4 closed
sprints on the same board, so the table shows 5 rows including current):

| Column | Definition |
|---|---|
| Sprint | Sprint name from the Sprint field |
| Capacity | SP across tickets that were in the sprint at `startDate` (committed). Unsized = 0. |
| Velocity | SP across tickets that reached `Done` while the sprint was active (use the changelog's `status → Done` timestamp, not the current ticket status, for closed sprints — items moved Done after the sprint closed don't count). |
| Overflow | `Capacity − Velocity` *(plus any added-mid-sprint SP that also didn't deliver, if you can compute it; otherwise just `Capacity − Velocity`)* |
| Scope Δ | Signed SP from sprint-field changelog: `+` SP added mid-sprint, `−` SP removed mid-sprint. Use `n/a` if changelog wasn't analyzed for that sprint. |
| Delivery% | `Velocity / Capacity * 100`, rounded. `n/a` if Capacity = 0. |

**Delivery% colour band** — apply one of these classes to the Delivery% cell:

- `delivered-high` (green, `var(--color-done)`) when `pct >= 80%`
- `delivered-mid` (blue, `var(--color-progress)`) when `50% <= pct < 80%`
- `delivered-low` (red-ish) when `pct < 50%`

**Empty cells** — if any of Capacity / Overflow / Scope Δ isn't available
for a past sprint (e.g. you ran a quick mode that skipped per-sprint
changelog analysis), render the cell as `<td class="empty">—</td>`. Don't
fake numbers. The Velocity column should always be populated — if it
can't be, drop the row entirely rather than half-fill it.

**Row order**: newest sprint at the TOP (matches reading order for "what
happened most recently"). Current sprint gets `class="current"` on its
`<tr>` and renders with a highlighted background + a small "current" chip
appended to the sprint name (CSS handles the chip).

**Ticket KPIs table** (the `{{TICKET_KPIS_HTML}}` placeholder):

```html
<table>
  <thead><tr>
    <th>Epic</th>
    <th>Done</th>
    <th>In Progress</th>
    <th>In Review</th>
    <th>In Testing</th>
    <th>PR Cycle</th>
    <th>Lead Time</th>
  </tr></thead>
  <tbody>
    <tr>
      <td><span class="epic-key-cell">RDUCH-41</span><span class="epic-name-cell">M2.1.8 ODC read-writing O11 data multi O11 infrastructures</span></td>
      <td>9</td>
      <td>3.2d</td><td>1.8d</td><td class="empty">—</td><td>1.6d</td><td>5.1d</td>
    </tr>
    …
    <tr class="epic-total">
      <td>…<span class="epic-name-cell">Sprint average (across epics)</span></td>
      <td>16</td>
      <td>…</td><td>…</td><td>…</td><td>…</td><td>…</td>
    </tr>
  </tbody>
</table>
```

**Per-metric definitions** (computed from each Done item's status-field
changelog; aggregate as a simple mean per epic, skipping items where the
metric is unavailable):

| Column | Definition |
|---|---|
| Epic | `parent.key` + `parent.fields.summary` (strip leading `[Tags]` for the name cell). |
| Done | Count of Done items in this epic this sprint. |
| In Progress | Avg days the ticket spent in status `In Progress`. From changelog: sum of (next-transition.created − In-Progress-entry.created) for each `In Progress` segment. |
| In Review | Avg days in `In Code Review` **or** `In Peer Review` (treat as the same phase — projects may use either label). |
| In Testing | Avg days in `In Testing`. `—` if the ticket skipped Testing. |
| PR Cycle | Days from first entry into a Review state to PR merge timestamp (read from `customfield_12600.cachedValue.summary.pullrequest.overall.lastUpdated` when `state == "MERGED"`). `—` when no PR is linked. |
| Lead Time | `resolutiondate − created` in days. |

**Colour bands** on every time cell:

- `class="fast"` (green) when value `< 1d` — fast turnaround.
- `class="slow"` (red) when value `> 5d` — likely a bottleneck.
- No class otherwise (default text colour).
- `class="empty"` for `—` cells (phase not observed for any item).

**Sample-size badge**: when fewer Done items have changelog data than the
`Done` count (e.g. the script skipped a few items), append a small
`<span class="sample-size">(n=N)</span>` to the Epic cell so the audience
knows the average is from a partial sample.

**Final row** is the sprint average across all epics, on a row with
`class="epic-total"` (highlighted background). Average **of epic
averages**, not of all individual items — this keeps a sprint with one
huge epic from drowning out the others.

A short footnote below the table explains the PR Cycle proxy. Keep the
note concise; reviewers know "PR Cycle = open → merge" intuitively.

**KPI bucket payload** (shape of `{{KPI_BUCKETS_JSON}}`):

```json
{
  "done":       [{"key":"RDUCH-189","summary":"...","status":"Done","sp":3,"assignee":"Martim Gouveia"}, ...],
  "carryover":  [{"key":"RDUCH-157","summary":"...","status":"Blocked","sp":5,"assignee":"...","reason":"blocked on open questions"}, ...],
  "scopeAdded": [],
  "bugs":       [],
  "unsized":    [{"key":"RDUCH-178","summary":"...","status":"To Do","sp":null,"assignee":"..."}]
}
```

- `done` is shared by both the **Completed SP** and **Velocity** cards (same underlying items, two metric views).
- `carryover` rows must include a `reason` string (same one-phrase reason used in the Carryover slide).
- `unsized` items have `sp: null`; the table renders `—`.
- Empty buckets are fine — the card stays clickable, the drawer opens with "No items in this bucket."
- Item fields are plain strings; the deck escapes them via `textContent` at render time, so do NOT pre-HTML-escape.

**Delivered-list epic grouping** (the `{{COMMITTED_DONE_LIST_HTML}}` placeholder):

```html
<li class="epic-group">
  <div class="epic-header">
    <span class="epic-key">RDUCH-188</span>
    <span class="epic-name">LT Connectivity — Cross-tenant DoS (RQ02)</span>
    <span class="epic-totals">3 of 5 items · 7 SP</span>
  </div>
  <div class="epic-progress">
    <div class="bar-track"><div class="bar-fill" style="width:60%"></div></div>
    <span class="bar-pct">60%</span>
  </div>
  <ul>
    <li><span class="item-key">RDUCH-189</span><span class="item-summary">M1 — AuthFailureCooldownService …</span><span class="item-sp">3 SP</span></li>
    <li><span class="item-key">RDUCH-177</span><span class="item-summary">Solution Design and LLD</span><span class="item-sp">2 SP</span></li>
    …
  </ul>
</li>
```

**Grouping rules:**

- One outer `<li class="epic-group">` per distinct parent Epic.
- Sort groups by **total SP descending**; ties broken by item count, then
  alphabetically by epic key.
- The `epic-name` is `parent.fields.summary` (strip leading `[Tags]` if it
  makes the header noisy — keep the human-readable portion).
- Items with no parent epic are collected into a final group with
  `epic-key` = `(no epic)` and no `epic-key` chip rendered.
- If there is only ONE distinct epic across all Done items, you may
  render a flat list instead of a single trivial group — your call.

**Progress bar per epic** (`<div class="epic-progress">`):

- The bar shows **in-sprint ticket completion** for this epic: numerator =
  Done items in this epic this sprint; denominator = ALL items in this
  epic this sprint (Done + in-flight + To Do + Blocked + carryover). So
  the denominator is bigger than the items listed inside the group —
  items not Done live in the Carryover section but still count in the
  total.
- `epic-totals` chip text: `"<done> of <total> items · <done_sp> SP"`
  (drop the percentage from the chip — it's on the bar's right-hand label).
- `bar-fill` class modifier:
  - default (green, `var(--color-done)`) when `pct >= 67%`
  - `.partial` (blue, `var(--color-progress)`) when `34% <= pct < 67%`
  - `.low` (amber, `var(--color-warn)`) when `pct < 34%`
- `width` on `bar-fill` is the inline percentage (e.g. `style="width:42%"`).
- `bar-pct` text is the percentage to the nearest integer.
- **Don't try to fetch the epic's children outside the sprint** — keep
  the percentage scoped to in-sprint completion. The point of this slide
  is what the sprint delivered against what the sprint planned for each
  epic, not lifetime epic completion.

**Demo-slide inner structure** (one section per **Epic** that has at least
one Done item in the sprint — *not* one per story):

```html
<section class="slide demo-slide epic-demo">
  <div class="eyebrow">Demo</div>
  <div class="demo-summary">
    <span class="demo-key">RDUCH-188</span>
    LT Connectivity — Cross-tenant DoS (RQ02)
  </div>
  <div class="epic-stats">
    <span>Done: <strong>1 of 4</strong> items (25%)</span>
    <span>Delivered: <strong>3 SP</strong> of 12</span>
    <span><a href="https://outsystemsrd.atlassian.net/browse/RDUCH-188" target="_blank">Open epic in Jira</a></span>
  </div>
  <ul class="epic-items">
    <li><span class="item-key">RDUCH-189</span><span class="item-summary">M1 — AuthFailureCooldownService …</span><span class="item-status">Done</span><span class="item-sp">3 SP</span></li>
    …
  </ul>
  <div class="epic-roster">
    <div class="roster-label">Worked by</div>
    <div class="roster-row">
      <figure class="dev-avatar">
        <div class="avatar-frame" data-color="3">
          <span class="initials">MG</span>
          <img src="https://www.gravatar.com/avatar/<md5(email)>?d=404&s=200"
               alt="Martim Gouveia"
               onerror="this.style.display='none'"
               loading="lazy">
        </div>
        <figcaption class="dev-name">Martim Gouveia</figcaption>
      </figure>
      …
    </div>
  </div>
</section>
```

**Epic demo-slide rules:**

- One slide per **distinct parent Epic** with at least one Done item in the
  sprint. Sort epics by Done SP desc, then total SP desc, then epic key.
- `epic-stats` shows: Done count vs total count, Done SP vs total SP, and a
  Jira link to the epic.
- `epic-items` lists every Done item in the epic (not all items — just Done),
  sorted by SP desc then key.
- `epic-roster` lists every developer who had at least one item assigned in
  this epic during the sprint (Done **or** in flight — the roster reflects
  who contributed, not just who closed work). Sort by display-name.
- Each developer renders as a `<figure class="dev-avatar">` containing an
  `<img>` (Gravatar by `md5(lowercased-trimmed-email)` with `d=404` so it
  fails to load when no Gravatar exists) layered over a gradient-coloured
  initials chip. The `onerror` handler hides the broken `<img>`, leaving the
  initials chip visible. `data-color="0..6"` picks one of the 7 gradient
  variants; the index should be deterministic from the name
  (`sum(ord(c) for c in name) % 7` works).
- **Avatar source caveat**: Slack profile-image URLs are not exposed by the
  Slack MCP wrapper. Gravatar is the working fallback for emails registered
  with Gravatar; otherwise the initials chip is the final rendering. If the
  user can drop avatar files into the repo, swap the `<img src>` to local
  paths instead.

The deck has these slides in order — **always render this exact set**, even
if a section is empty (use a "Nothing to report" line in that slide rather
than dropping it, so the meeting flow stays predictable):

1. **Title** — team, sprint name, dates, goal
2. **Sprint goal & outcome** — one big line: Achieved / Partially / Not / No goal, plus a one-sentence reason
3. **Numbers at a glance** — KPI grid: Committed SP, Completed SP, Velocity vs. avg, Bugs, Scope added, Unsized
4. **Burndown / velocity chart** — Chart.js doughnut for completion split + bar for velocity history
5. **What we delivered** — `Committed & Done` list, max 10 items per slide; auto-paginate if more
6. **Demo slides** — one slide per **parent Epic** that has at least one Done item this sprint. Each slide has the epic header, Done items list, and a "Worked by" roster of round developer avatars (Gravatar + initials fallback) for everyone who had an item in the epic this sprint
7. **Scope changes** — `Added & Done` and `Added & Carryover` and `Removed` combined; collapsed to "No scope changes this sprint" if all three are empty
8. **Carryover** — `Committed & Carryover` with reasons
9. **Next sprint preview** — top items if `state=future` sprint exists, else placeholder
10. **Q&A / Discussion** — closing slide with Slack channel URL for follow-up

#### 7a. Sub-epic rollup (optional, configurable per team)

Some teams use a two-level epic hierarchy: a "feature" or "milestone"
ticket parents several smaller epics that each parent the actual stories.
Example from RDUCH:

- `RDUCH-169` PU-M4.13.1 Private O11 LifeTime-to-ODC Connectivity *(feature)*
  - `RDUCH-182` [RQ01] Tenant-specific service accounts *(sub-epic)*
    - `RDUCH-183`, `RDUCH-184`, … *(stories)*
  - `RDUCH-188` [RQ02] Cross-tenant DoS — auth-failure cooldown *(sub-epic)*
    - `RDUCH-189`, `RDUCH-190`, … *(stories)*

Each story's `parent.key` points at the sub-epic. Grouping naïvely splits
the feature into multiple lines across the Delivered list, Demo slides,
Scope-changes slide, Carryover, Next sprint, and the Ticket KPIs table —
which dilutes the picture the stakeholders care about.

Fix: configure a rollup map at the top of the renderer and apply it
in-place to every loaded item before grouping:

```python
EPIC_ROLLUP = {
    "RDUCH-182": ("RDUCH-169", "PU-M4.13.1 Private O11 LifeTime-to-ODC Connectivity"),
    "RDUCH-188": ("RDUCH-169", "PU-M4.13.1 Private O11 LifeTime-to-ODC Connectivity"),
}

def apply_epic_rollup(item_list):
    for i in item_list:
        rolled = EPIC_ROLLUP.get(i.get("parent_key"))
        if rolled:
            i["parent_key"], i["parent_summary"] = rolled
```

**Rules:**

- Apply to **every** item list: current sprint items, future sprint items,
  closed-sprint history (where epic grouping matters). Do **not** mutate
  the items' own keys/summaries — only the `parent_key` / `parent_summary`
  pair.
- Jira links on each story stay intact; drilling in still lands on the
  real sub-epic. The rollup is purely presentation.
- The map is **team-specific configuration**, not data-driven. Ask the
  user which sub-epics roll up into which parents before the first render
  for a new team. Add new entries as new feature breakdowns appear.
- The Ticket KPIs table averages then include all child items under the
  parent, so the sample size is larger and the metrics are more
  representative — a feature with 5 items across 2 sub-epics gives a
  better signal than two single-item averages.
- If a project uses Jira's native parent-of-epic relationship and you
  want to auto-discover the map, query the parent of each epic key
  (`getJiraIssue <EPIC-KEY> --fields parent`). For most teams the static
  map is simpler and easier to review.

#### 7b. Burndown chart data (optional)

If you can pull the sprint's daily Done-SP history, pass it as
`{{BURNDOWN_JSON}}`. Otherwise pass `null` — the template hides the chart
cleanly.

Quickest approach: walk the changelog of every Done ticket, find the
`status → Done` transition timestamp, group SP by day from `startDate` to
`endDate`, then cumulate. Shape:

```javascript
{
  startDate: "2024-05-06",
  endDate:   "2024-05-19",
  committedSP: 42,
  idealLine: [42, 39, 36, ..., 0],   // straight line, len = sprint days
  actualLine: [42, 42, 40, ..., 7]   // remaining SP each day
}
```

Skip this if it's the day-of-review and the data isn't precomputed —
the deck still works without it, the chart is hidden.

### Step 8 — Output, open, and report back

Write both files into the current working directory:

- `<CWD>/sprint-review-<SAFE_SPRINT_NAME>.md`
- `<CWD>/sprint-review-<SAFE_SPRINT_NAME>.html`

Open the deck for preview:

```bash
open "<CWD>/sprint-review-<SAFE_SPRINT_NAME>.html"
```

Tell the user:
- Both absolute paths
- The sprint name and goal outcome verdict you chose
- That the deck is keyboard-navigable (`→` / `space` next, `←` previous,
  `F` fullscreen, `P` print) and the report is ready to paste into Slack
  or Confluence
- Slack channel URL for sharing
- Whether the average-velocity comparison used 3 prior sprints (or fewer,
  with a note about confidence)

## Best Practices

1. **Explicit sprint, never silent default.** If the user didn't name a
   sprint, ask. Don't pick up an active sprint and hope.

2. **Both artifacts from one data pull.** Resolve and metric the sprint
   once; render both files from the same in-memory data model. Don't
   re-query for the deck.

3. **Carryover reasons must be honest.** Every carryover row needs a
   one-phrase reason (`blocked on review`, `scope grew`, `unsized & not
   started`, etc.). "Not finished" is not a reason.

4. **Goal outcome verdict is your call.** Use this rubric, but don't
   apply it mechanically:
   - **Achieved** = goal explicit AND completion ≥ 80% AND no critical
     scope slipped to carryover
   - **Partially achieved** = goal explicit AND completion 50-80%, OR
     completion ≥ 80% but a critical scope item slipped
   - **Not achieved** = goal explicit AND completion < 50%, OR the goal
     story itself is in carryover
   - **No goal** = no sprint goal recorded

5. **Demo slides have one assignee, one PR link, one empty notes line.**
   Don't try to write the demo content yourself — the presenter speaks
   to it live. Keep it scannable.

6. **Velocity comparison needs ≥ 3 sprints to be honest.** If fewer
   prior sprints exist, say so on the slide rather than averaging 1.

## Common Mistakes

### ❌ Reporting velocity without subtracting added-mid-sprint
Velocity is *completed SP*, regardless of when work entered the sprint.
But the **commitment-vs-delivery** percentage MUST use only the original
committed set. Show both — completion of commitment AND total SP delivered.

### ❌ Burying carryover in a footnote
This is the most important slide for stakeholders. Give it its own slide
with reasons.

### ❌ Picking the wrong sprint when there are multiple active
A board can have multiple sprints in `state=active` (team + sub-team).
Always confirm the sprint name and ID after resolution before rendering.

### ❌ Treating "Added & Done" as a win without flagging the scope change
Stakeholders care about what was promised, not just total throughput.
Show scope additions on their own line.

### ❌ Posting to Slack on the user's behalf
The skill does NOT post. It surfaces the channel URL and lets the user
share manually.

## Quick Reference

| Step | Command |
|---|---|
| Sprint tickets by name | `acli jira workitem search --jql 'sprint = "<NAME>"' --fields "..." --csv --limit 200` |
| Sprint tickets by ID | `acli jira workitem search --jql 'sprint = <ID>' --fields "..." --csv --limit 200` |
| Resolve sprint metadata | `acli jira workitem view <KEY> --fields '*all' --json \| jq '.fields.customfield_10006'` |
| Find "last closed" sprint | `acli jira workitem search --jql 'sprint in closedSprints() AND project = <PROJ> ORDER BY endDate DESC'` |
| Get changelog (mid-sprint adds) | `acli jira workitem view <KEY> --fields '*all' --expand changelog --json` |
| Avg-velocity sample | `acli jira workitem search --jql 'sprint in closedSprints() AND project = <PROJ> AND status = Done'` |
| Confluence team page | `koda tool confluence get --page-id 5852397579` |
| Open deck | `open <path-to-sprint-review-*.html>` |

## Reference Files

| File | Purpose |
|---|---|
| [reference/data-sources.md](reference/data-sources.md) | Sprint custom-field IDs, JQL patterns, sprint blob format, team defaults |
| [reference/report-template.md](reference/report-template.md) | Markdown report template with placeholders |
| [reference/presentation-template.html](reference/presentation-template.html) | Self-contained HTML slide deck template |
