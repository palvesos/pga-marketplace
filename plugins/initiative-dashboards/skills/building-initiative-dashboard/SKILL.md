---
name: building-initiative-dashboard
description: >-
  Builds a self-contained interactive HTML dashboard summarising the progress
  of an initiative or epic — including Story Points roll-up, status
  distribution, per-track breakdown, linked GitHub PRs, Productboard feature
  context, Confluence design and UX page links, Google Sheets roadmap
  priority, an executive Progress Summary and Recommended Actions. Use when
  the user asks to "build a dashboard for initiative X", "create a progress
  dashboard for epic Y", "make a status dashboard for RDUCH-169", "executive
  report for PU-M4.13.1", or "visualise progress on an initiative".
allowed-tools: Bash(acli jira:*),Bash(gh search:*),Bash(gh pr:*),Bash(npx:*),Bash(open:*),Bash(mkdir:*),Bash(ls:*)
---

# Building an Initiative Dashboard

## When to Use

**Use this skill when the user asks to:**
- Build a dashboard, progress report, or executive update for an initiative or epic
- Visualise the status of an epic and its children (Jira tree walk)
- Pull together Jira + GitHub PRs + Productboard + Confluence + roadmap context
  into a single shareable HTML file
- Generate a self-contained dashboard for delivery managers, EMs, or PMs

**Do NOT use for:**
- Single-ticket status queries → use `tooling-kit:jira` directly
- General BI dashboards over data warehouse data → use `data:build-dashboard`
- Live always-on dashboards → this generates a point-in-time HTML snapshot

## Prerequisites

1. `acli` authenticated against Atlassian (`acli jira auth status`)
2. `gh` authenticated against GitHub (`gh auth status`)
3. `prodeng-productboard` configured (optional — needed only if PB feature is included)
4. `prodeng-drive-cli` authenticated (optional — needed only if roadmap sheet is included)
5. A starting **Jira epic or initiative key** (e.g. `RDUCH-169`, `RPOR-28605`)

## Workflow

### Step 1 — Gather the initiative tree from Jira

Walk the Jira hierarchy starting from the user-provided key.

```bash
# Main epic / initiative details
acli jira workitem view <KEY> --fields '*all' --json

# Direct children
acli jira workitem search --jql "\"Epic Link\" = <KEY> OR parent = <KEY>" \
  --fields "key,summary,status,assignee,issuetype" --csv

# Linked epics (for cross-team or sibling work)
acli jira workitem search --jql "issue in linkedIssues(<KEY>)" \
  --fields "key,summary,status,assignee,issuetype" --csv

# For each linked epic, fetch its children too
acli jira workitem search --jql "\"Epic Link\" = <LINKED_EPIC> OR parent = <LINKED_EPIC>" \
  --fields "key,summary,status,assignee,issuetype" --csv
```

For each ticket, extract:
- `key`, `summary`, `status.name`, `assignee.emailAddress`, `issuetype.name`
- **Story Points** from `customfield_10004`
- **Parent / Epic Link** from `customfield_10007`
- **PR linkage** from `customfield_12600` (regex: `state=([A-Z]+)`, `stateCount=(\d+)`)

See **[reference/data-sources.md](reference/data-sources.md)** for the full
list of useful custom field IDs and commands.

### Step 2 — Resolve linked PRs from GitHub

For tickets where the dev-info field shows a PR exists. `gh search prs`
only accepts `--state open` or `--state closed` (no `all`). For each
ticket, run **two queries** and concatenate the results:

```bash
# Open PRs (default — no --state flag)
gh search prs "<TICKET-KEY>" --limit 5 \
  --json url,title,state,repository,isDraft

# Closed / merged PRs
gh search prs "<TICKET-KEY>" --limit 5 --state closed \
  --json url,title,state,repository,isDraft
```

If the dev-info field only reports `state=OPEN`, the second query can be
skipped to save calls. For `Done` tickets, run the closed query to surface
the merged PR.

For each found PR, optionally fetch detail:

```bash
gh pr view <NUMBER> --repo <OWNER>/<REPO> \
  --json url,title,state,isDraft,additions,deletions,reviewDecision,statusCheckRollup
```

### Step 3 — Fetch optional context

**Productboard feature** (if the user passed a PB UUID, or one is linked from
Jira/Confluence):

```bash
npx -y github:OutSystems/prodeng-productboard list_feedback \
  --args '{"featureId":"<UUID>"}'
```

**Confluence design and UX pages** (if linked from the epic description or
session notes):

```bash
# Use the koda confluence tool to fetch page content
koda tool confluence get --page-id <ID>
```

**Google Sheet roadmap row** — discover the headers first, then find the
initiative's row:

```bash
# Read headers (row 1)
npx -y github:OutSystems/prodeng-drive-cli sheets read <SHEET_ID> '1:1'

# Then fuzzy-match column names like:
#   "Initiative" / "ID" / "Jira" / "PB ID"  → for the row lookup key
#   "Priority" / "Rank" / "VS Rank"          → priority signal
#   "Quarter" / "Target" / "ETA"             → timing signal
# Read the matching row(s) for the initiative
npx -y github:OutSystems/prodeng-drive-cli sheets read <SHEET_ID> '<ROW>:<ROW>'
```

If credentials are missing for any optional source, **skip it gracefully**
and note the gap in the Progress Summary.

### Step 4 — Synthesise the dashboard data model

Build a JSON array of items with this shape:

```javascript
{
  key: "RDUCH-183",
  type: "Story",
  summary: "...",
  status: "In Progress",
  sp: 2,                       // null if unsized
  assignee: "user@x",          // "-" if unassigned
  track: "RQ01",               // workstream — derived from parent epic or summary tag
  team: "Unification Charlie", // engineering team — derived from project prefix
  prUrl: "https://...",        // null if no PR
  prState: "OPEN",             // null if no PR
  prRepo: "Repo#473"           // null if no PR
}
```

**Track classification** (workstream / requirement bucket):
- Parent / Epic Link grouping
- Summary tags like `[RQ01]`, `[RQ02]`
- Use a sensible "context" bucket for parent VMs or unrelated context

**Team classification** (engineering team / Jira project owner):
Derive from the Jira project prefix using this default mapping (extend
as needed):

| Prefix | Team |
|---|---|
| RDUCH | Unification Charlie |
| RDUCO | Unification Consoles |
| RDUCV | Unification Vega |
| RDUC* (other) | Unification \<other\> |
| RPOR | Portfolio |
| RDSHDT | Self-Hosted DT |
| RDSD | Solution Design |
| (unknown) | use the prefix verbatim |

When in doubt, ask the user to confirm the track and team mappings
before rendering.

### Step 5 — Draft the executive narrative

The dashboard has **four narrative blocks**. Author all of them.

#### 5.1 Hero row (top of dashboard, 3 cards)

**Card 1 — Status traffic light**
- `RAG_STATUS`: one of `green`, `yellow`, `red` (lowercase, no quotes)
- `RAG_LABEL`: short label, e.g. `On Track`, `At Risk`, `Off Track`,
  `Pre-implementation`
- `RAG_HEADLINE`: one short sentence explaining the colour

**Card 2 — Executive Status** (3-5 short bullets)

**Hard limit: 60 words total** across all bullets. Count every word
in the rendered text. If over, cut — don't soften the constraint.

Use a `<ul>` of `<li>` bullets. Each bullet is one factual sentence.
Group team-progress bullets first, then open-question bullets prefixed
with `Open question:` (or `Open decision:`) so the reader can scan
progress vs. risks at a glance.

**Voice and audience.** Written as if by an **Engineering Director**
presenting to **C-level Leadership** and **Product Management Leadership**.
Strategic, outcome-oriented, calm. The reader is not in the day-to-day.

**Tone rules:**
- **Synthetic** — distilled to essence. No qualifying adjectives ("very
  important", "key milestone"), no filler phrases ("it's worth noting
  that…", "as previously mentioned…").
- **Objective** — statements of fact only. Avoid editorial language like
  "warrants attention", "concerning", "encouraging progress", "we are
  pleased that…". The RAG card already carries the editorial signal.

**Content rules:**
- **DO** name the **teams** involved and describe their progress at the
  workstream level (e.g. "Unification Charlie completed the design phase
  for RQ01 and RQ02 and has started implementation; Unification Consoles
  is delivering the dependent Portal changes").
- **DO** frame the watch items as **open design questions or pending
  decisions** that leadership can help unblock (e.g. "the third
  requirement still lacks an approved design", "scope of validation
  pending alignment between Team A and Team B").
- **DO NOT** mention PR numbers, PR review state, Jira ticket keys, or
  ticket-level status. That detail lives in the Progress Summary and the
  table below.
- **DO NOT** use shorthand like "M1 in review" or "RDUCH-183 in peer review".
- **Bullets 1-3: team / workstream progress** — what each named team
  did most recently. Keep each bullet to a single sentence.
- **Bullets 4-5: open design questions or decisions** — prefix with
  `Open question:` or `Open decision:` for scannability.

**Card 3 — Highlights / Lowlights**
- **Up to 3 highlights** (`<ul>` under an `<h4>Highlights</h4>`) — the
  most important recent wins. **Hard cap: 3.**
- **Up to 3 lowlights** (`<ul>` under an `<h4>Lowlights</h4>`) — the
  most important risks, blockers, or slips. **Hard cap: 3.**
- If more than 3 candidates exist, pick the highest-impact ones for an
  executive audience and drop the rest. Don't soften — cut.
- **DO NOT** include PR idle / review-SLA observations such as "PRs idle
  in review for >24h" or "review SLA breached". PR review hygiene
  belongs in the Progress Summary below, not in the hero. The same rule
  applies to all three hero cards (RAG, Executive Status, and this one).
- Both sections wrapped in `<div class="hl-section highlights">` /
  `<div class="hl-section lowlights">` so the CSS picks up the right
  badges.

#### 5.2 Progress Summary (bottom row, left card)

Bulleted executive prose for Engineering Directors and PMs. 6-10 bullets:
- Headline RAG with a one-line summary
- Quantified scope progress (% delivered / in flight / remaining of sized SP)
- Per-track RAG (Green/Yellow/Red with one-line justification each)
- Cross-team execution health
- Open risks for leadership attention (as a nested bullet group)
- Next milestone (the one gate that clears the biggest current flag)

#### 5.3 Recommended Actions (bottom row, right card)

5-7 concrete, owner-assignable bullets. Each should name a Jira key, PR,
or owner — no vague guidance.

### Step 6 — Render and open the dashboard

1. Read the template from
   [reference/dashboard-template.html](reference/dashboard-template.html)
2. Substitute the placeholders:
   - `{{INITIATIVE_TITLE}}` — e.g. "PU-M4.13.1 — Private O11 LifeTime-to-ODC Connectivity"
   - `{{INITIATIVE_SUBTITLE}}` — Productboard link, Confluence links, Jira epic.
     **Productboard ID must render as a clickable link.** URL pattern
     for OutSystems: `https://outsystems.productboard.com/entity-detail/features/<uuid>`.
     If the parent Jira ticket has a Productboard URL in its
     `customfield_15504` (or similar Productboard-link custom field),
     prefer that URL verbatim over constructing one from the UUID.
   - `{{ITEMS_JSON}}` — the JSON array from Step 4
   - **Hero row (from Step 5.1):**
     - `{{RAG_STATUS}}` — `green` | `yellow` | `red` (lowercase)
     - `{{RAG_LABEL}}` — e.g. `On Track`, `At Risk`, `Off Track`
     - `{{RAG_HEADLINE}}` — one-sentence justification
     - `{{EXEC_STATUS_REPORT_HTML}}` — 1-2 `<p>` paragraphs, no bullets
     - `{{HIGHLIGHTS_LOWLIGHTS_HTML}}` — two `<div class="hl-section …">` blocks
   - `{{PROGRESS_SUMMARY_HTML}}` — `<ul>...</ul>` of bullets
   - `{{RECOMMENDED_ACTIONS_HTML}}` — `<ul>...</ul>` of bullets
   - `{{SNAPSHOT_DATE}}` — today's date (YYYY-MM-DD)
   - `{{SOURCES_LINE}}` — comma-separated list of sources actually queried
**Filters in the dashboard header (fixed set):**
- **Track** — workstream filter, populated from `item.track`
- **Team** — engineering team filter, populated from `item.team`
- No Status filter, no Assignee filter (both removed; that detail is
  visible in the item table and the doughnut chart).

3. Write to `<INITIATIVE_FOLDER_OR_CWD>/dashboard.html`
4. Open it: `open <path>` (macOS)
5. Tell the user the path and what the dashboard contains

## Best Practices

1. **One Jira key is the only required input** — everything else (PB UUID,
   Confluence pages, roadmap row) is discovered or optional. Don't block on
   missing optional context; mention the gap in the summary.

2. **Always show the SP roll-up explicitly** — Done / In Flight /
   To Do (sized) / Unsized. Three buckets without "Unsized" lies about scope.

3. **RAG must be defensible** — Green/Yellow/Red per track must have a
   one-line reason that an EM can repeat in a meeting. No "Yellow because vibes".

4. **Sequencing risks are first-class** — if M-stories are In Progress before
   their LLD is Done, call it out as Yellow in the summary.

5. **Never invent data** — if PB or Confluence wasn't queryable, omit the
   section rather than fabricating it.

## Common Mistakes

### ❌ Reporting "100% complete" using only Done items
The denominator must include unsized items as a known unknown.
→ **Always include an "Unsized items" KPI on the dashboard.**

### ❌ Hardcoding tracks from prior runs
Track buckets vary by initiative.
→ **Derive tracks from epic structure each time; ask the user to confirm if ambiguous.**

### ❌ Skipping the Auto-open step
The user expects to see the file open in their browser.
→ **Run `open <path>` after writing the file. Report the absolute path too.**

### ❌ Burying the headline in a paragraph
This is for executives.
→ **Lead the Progress Summary with a one-line RAG + headline.**

## Quick Reference

| Step | Command |
|---|---|
| Get epic + fields | `acli jira workitem view <KEY> --fields '*all' --json` |
| Get children | `acli jira workitem search --jql "\"Epic Link\" = <KEY> OR parent = <KEY>"` |
| Get linked epics | `acli jira workitem search --jql "issue in linkedIssues(<KEY>)"` |
| Find open PRs for ticket | `gh search prs "<KEY>"` (default = open) |
| Find merged/closed PRs | `gh search prs "<KEY>" --state closed` |
| Get PR detail | `gh pr view <N> --repo <O>/<R> --json ...` |
| Read sheet headers | `npx -y github:OutSystems/prodeng-drive-cli sheets read <ID> '1:1'` |
| List PB feedback | `npx -y github:OutSystems/prodeng-productboard list_feedback --args '{"featureId":"<UUID>"}'` |
| Open dashboard | `open <path-to-dashboard.html>` |

## Reference Files

| File | Purpose |
|---|---|
| [reference/data-sources.md](reference/data-sources.md) | Custom field IDs, JQL patterns, and per-source command details |
| [reference/dashboard-template.html](reference/dashboard-template.html) | The HTML template with substitution placeholders |
