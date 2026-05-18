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
  PRs). Use when the user asks to "build a portfolio dashboard for
  initiatives X, Y, Z", "rollup status for value milestone VM-123",
  "executive rollup for these initiatives", "VM status dashboard", or
  "summary across multiple initiatives".
allowed-tools: Bash(acli jira:*),Bash(gh search:*),Bash(gh pr:*),Bash(open:*),Bash(mkdir:*),Bash(ls:*)
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
- Render the per-initiative dashboard to
  `<output-dir>/dashboard-<KEY>.html`
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

### Step 4 — Draft the portfolio executive summary

**Audience:** C-level + PM Leadership, same voice as the per-initiative
exec status (Engineering Director, synthetic, objective).

**Format:** 3-5 short `<li>` bullets, **hard cap 80 words total**
across all bullets. The cap is wider than per-initiative (60) because
a portfolio summary needs to cover more ground.

**Content:**
- Overall portfolio posture in one bullet
- Cross-cutting wins or risks shared across multiple initiatives
- The single most important leadership-attention item

Same banned vocabulary applies (no `warrants attention`,
`encouraging`, etc.). No PR review-SLA noise. No Jira ticket keys.

### Step 5 — Render the portfolio dashboard

1. Read the template at
   [reference/portfolio-template.html](reference/portfolio-template.html)
2. Substitute the placeholders:
   - `{{PORTFOLIO_TITLE}}` — e.g. "Q2 Initiatives Portfolio" or the VM
     name if the input was a VM
   - `{{PORTFOLIO_SUBTITLE}}` — e.g. "Status of N initiatives ·
     YYYY-MM-DD" plus the input echo (VM key or comma-separated keys)
   - `{{KPI_*}}` — the seven KPI values from Step 3
   - `{{INITIATIVE_CARDS_HTML}}` — concatenated HTML of all initiative
     cards (see card structure below)
   - `{{INITIATIVES_INDEX_JSON}}` — JSON array driving the filterable
     **Initiatives Index** table. One object per initiative:
     ```json
     {
       "key": "RDUCH-169",
       "title_short": "PU-M4.13.1 LT Connectivity",
       "rag_status": "green",
       "rag_label": "Green",
       "team": "Unification Charlie",
       "rpor_key": "RPOR-28605",
       "rpor_label": "PU-M4.13"
     }
     ```
     The table renders Initiative title (linked to the per-initiative
     dashboard), RAG pill, owner team, and parent RPOR. Filters at the
     top let the user narrow by **Owner Team** and **Parent RPOR**.
   - `{{PORTFOLIO_EXEC_HTML}}` — the `<ul>...</ul>` from Step 4
   - `{{SNAPSHOT_DATE}}` — today's date
   - `{{SOURCES_LINE}}` — which sources were queried per initiative
3. Write to `<output-dir>/portfolio-dashboard.html`
4. Open it: `open <path>`

#### Initiative card structure

Each initiative becomes one `<article class="initiative-card">` with:

```html
<article class="initiative-card rag-{{RAG_STATUS}}">
  <header class="card-header">
    <span class="rag-dot rag-dot-{{RAG_STATUS}}"></span>
    <h2><a href="dashboard-{{KEY}}.html">{{TITLE}}</a></h2>
    <div class="card-meta">
      <a href="https://outsystemsrd.atlassian.net/browse/{{KEY}}">{{KEY}}</a>
      · <a href="dashboard-{{KEY}}.html">view full →</a>
    </div>
    <div class="rag-headline">{{RAG_HEADLINE}}</div>
  </header>
  <section class="card-exec">
    <h4>Executive Status</h4>
    <ul>{{EXEC_BULLETS}}</ul>
  </section>
  <section class="card-hl">
    <div class="hl-section highlights">
      <h4>Highlights</h4><ul>{{HIGHLIGHTS}}</ul>
    </div>
    <div class="hl-section lowlights">
      <h4>Lowlights</h4><ul>{{LOWLIGHTS}}</ul>
    </div>
  </section>
</article>
```

The card always links to the per-initiative `dashboard-<KEY>.html`
generated in Step 2 — that's the drill-down path.

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

## Quick Reference

| Step | Command |
|---|---|
| Detect VM | `acli jira workitem view <KEY> --fields "issuetype" --json` |
| Find VM children (epics) | `acli jira workitem search --jql "\"Epic Link\" = <VM> OR parent = <VM> OR issue in linkedIssues(<VM>)"` |
| Per-initiative drilldown | Follow `building-initiative-dashboard` SKILL.md |
| Render | Substitute template placeholders, write `portfolio-dashboard.html` |
| Open | `open <path>` |

## Reference Files

| File | Purpose |
|---|---|
| [reference/portfolio-template.html](reference/portfolio-template.html) | The portfolio HTML template with placeholders |

The inner skill (`building-initiative-dashboard`) provides:
- `reference/data-sources.md` — per-initiative data source commands
- `reference/dashboard-template.html` — per-initiative HTML template
