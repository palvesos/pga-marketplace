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
  | jq '.fields.customfield_10010 // .fields.sprint // empty'
```

The Sprint field is an array of sprint blobs containing `id`, `name`,
`state` (`active`/`closed`/`future`), `startDate`, `endDate`, `goal`, and
`boardId`. Use this to populate the sprint header (name, dates, goal) in
both artifacts.

If the field ID `customfield_10010` isn't populated for your instance, fall
back to `.fields.sprint` or grep the raw output for `com.atlassian.greenhopper`.
See **[reference/data-sources.md](reference/data-sources.md)** for full
details on the sprint blob format and OutSystems-specific field IDs.

### Step 2 — Pull the ticket detail you need

For every ticket in the sprint, capture:

- `key`, `summary`, `status.name`, `assignee.displayName` (or emailAddress),
  `issuetype.name`, `priority.name`, `labels[]`
- **Story Points** from `customfield_10004`
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

In the JSON, `changelog.histories[].items[]` where `field == "Sprint"` shows
which sprint(s) the ticket moved in/out of, with timestamps. A ticket
**added mid-sprint** is one whose Sprint field was set to the current
sprint *after* the sprint's `startDate`. Mark it `added_mid_sprint: true`
so the report can break out "scope changes".

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
  --fields "key,customfield_10004,customfield_10010" \
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
| `{{COMMITTED_DONE_LIST_HTML}}` | `<li>` rows for the "What we shipped" slide. Each: `<li><span class="item-key">KEY</span><span class="item-summary">summary</span><span class="item-sp">N SP</span></li>` |
| `{{SCOPE_CHANGES_HTML}}` | Three small sections: Added & Done, Added & Carryover, Removed. If all three empty: render `<div class="empty-state">No scope changes this sprint.</div>` |
| `{{CARRYOVER_LIST_HTML}}` | `<li>` rows like the delivered list, plus an `<span class="item-reason">…</span>` with the one-phrase reason. Empty-state line if nothing carried over. |
| `{{NEXT_SPRINT_HTML}}` | `<li>` rows for the next-sprint preview. Empty-state line if no future sprint. |
| `{{COMMITTED_DONE_SP}}` / `{{ADDED_DONE_SP}}` | Raw numbers (SP) for the doughnut chart on slide 4 |
| `{{BURNDOWN_JSON}}` | Optional — see Step 7b. Pass `null` (literal, no quotes) to skip the burndown line chart; the template will fall back to the velocity-history bar instead. |
| `{{VELOCITY_HISTORY_JSON}}` | Array `[{name, sp, current}]` for prior closed sprints + this one (`current:true` on the most recent). Pass `[]` to hide the fallback too. |

**Demo-slide inner structure** (one section per Done story):

```html
<section class="slide demo-slide">
  <div class="demo-summary"><span class="demo-key">RDUCH-183</span> Story summary text here</div>
  <div class="demo-meta">
    <span>Assignee: <strong>Jane Doe</strong></span>
    <span>SP: 3</span>
    <span>Status: Done</span>
    <span><a href="https://github.com/.../pull/123" target="_blank">PR #123 (merged)</a></span>
  </div>
  <div class="demo-notes"></div>
</section>
```

The `demo-notes` div is intentionally empty — the presenter speaks to it
live. CSS prepends a "Speaker notes" label automatically.

The deck has these slides in order — **always render this exact set**, even
if a section is empty (use a "Nothing to report" line in that slide rather
than dropping it, so the meeting flow stays predictable):

1. **Title** — team, sprint name, dates, goal
2. **Sprint goal & outcome** — one big line: Achieved / Partially / Not / No goal, plus a one-sentence reason
3. **Numbers at a glance** — KPI grid: Committed SP, Completed SP, Velocity vs. avg, Bugs, Scope added, Unsized
4. **Burndown / velocity chart** — Chart.js doughnut for completion split + bar for velocity history
5. **What we delivered** — `Committed & Done` list, max 10 items per slide; auto-paginate if more
6. **Demo slides** — one slide per Done story (committed first, then added), with: key, summary, assignee, PR link if present, and an empty "Demo notes" placeholder so the presenter can speak to it
7. **Scope changes** — `Added & Done` and `Added & Carryover` and `Removed` combined; collapsed to "No scope changes this sprint" if all three are empty
8. **Carryover** — `Committed & Carryover` with reasons
9. **Next sprint preview** — top items if `state=future` sprint exists, else placeholder
10. **Q&A / Discussion** — closing slide with Slack channel URL for follow-up

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
| Resolve sprint metadata | `acli jira workitem view <KEY> --fields '*all' --json \| jq '.fields.customfield_10010'` |
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
