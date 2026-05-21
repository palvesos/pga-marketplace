# Session Resume — `claude/scrum-sprint-review-skill-3BDYG`

> Transient handoff notes for resuming the in-flight Sprint Review skill work
> after a session restart. Specific to this branch. Delete when the branch
> merges.

## Where we left off

- **Branch:** `claude/scrum-sprint-review-skill-3BDYG`
- **Last commit:** `a501559` (Sprint review deck: sprint history table on the Trends slide)
- **Working tree:** clean. Generated dryrun artifacts live under
  `sprint-review-rduch-26q2-4.{md,html}` at repo root but are `.gitignore`d.
- **Blocker:** Atlassian MCP was disconnected, then re-installed but the
  OAuth flow has not completed end-to-end. The `authenticate` tool is
  rate-limited so re-bootstrap from this side is not currently possible —
  see *Atlassian MCP auth* below.

## What's built (commits on this branch, oldest → newest)

| Commit | What it landed |
|---|---|
| `7280a28` | Initial `scrum-ceremonies` plugin + `building-sprint-review` skill. SKILL.md, data-sources.md, presentation-template.html, report-template.md. Marketplace + README updated. Activation tests. |
| `acf94fb` | `.gitignore` for skill-generated outputs (`sprint-review-*.md`, `*.html`, plus dashboard outputs). |
| `44a7394` | Chrome fix: nav buttons / counter / hint now sit on dark pills, readable on white slides. |
| `2a93579` | "What we shipped" slide: group Done items by parent Epic. SKILL.md instructs the search to pull `parent` + `customfield_10007`. |
| `105ffdc` | Per-epic progress bar showing in-sprint ticket completion (Done / total in-sprint). Colour band ≥67% green, ≥34% blue, <34% amber. |
| `0d24f7d` | "By the numbers" KPI cards are now clickable; click expands an item table below the grid. New `{{KPI_BUCKETS_JSON}}` placeholder powers the drilldown. |
| `a501559` | Trends slide: sprint-history table below the two charts. Columns: Sprint · Capacity · Velocity · Overflow · Scope Δ · Delivery%. Current sprint highlighted. |

## Files of interest

- `plugins/scrum-ceremonies/skills/building-sprint-review/SKILL.md` — the
  full skill, including all the placeholder tables and grouping rules.
- `plugins/scrum-ceremonies/skills/building-sprint-review/reference/presentation-template.html` — the HTML deck template (50 KB after the
  latest edits; ~700 lines).
- `plugins/scrum-ceremonies/skills/building-sprint-review/reference/report-template.md` — the Markdown report template.
- `plugins/scrum-ceremonies/skills/building-sprint-review/reference/data-sources.md` — Jira field IDs, JQL patterns, team defaults.

## Pending work

When the Atlassian MCP is authenticated and you reply "ready", re-pull
RDUCH 26.Q2.4 with the corrections the dryrun couldn't make. In order:

1. **Re-query with the right fields.** Use `customfield_10006` for Sprint
   (not `_10010` — see *Skill bugs* below), and request `parent` +
   `customfield_10007` so Done items group by real epic key + summary
   instead of the heuristic `[Tag]` prefix the dryrun used.

2. **Walk the sprint-field changelog.** `--expand changelog` (or the MCP
   equivalent) on each in-sprint ticket. From the changelog:
   - Detect **added mid-sprint** (`Sprint` field set to current sprint
     after `startDate`) → populates the *Added & Done* table and the
     *Scope changes* slide.
   - Detect **removed mid-sprint** → also feeds the Scope changes slide.
   - Detect the **status → Done timestamp** for past sprints → fixes the
     Velocity column on the sprint-history table (the dryrun
     over-attributed carried-over work to the closing sprint).

3. **Compute proper past-sprint metrics.** For the last 4 closed sprints
   on board 7404 (RDUCH), fill Capacity / Velocity / Overflow / Scope Δ /
   Delivery% in the sprint-history table. The dryrun left those as `—`
   for past sprints — see the italic footnote on the current slide 4.

4. **Pull the future sprint.** `sprint in futureSprints() AND project =
   RDUCH` — populate the "Next sprint preview" slide instead of the
   empty-state placeholder.

5. **PR linkage on demo slides.** `gh` is NOT installed in this remote
   container, so the production-quality approach is the dev-info field
   (`customfield_12600`) which already shows `state=MERGED/OPEN` and
   `stateCount=N` on each ticket. Surface that as a small badge on the
   demo slide even without the URL. If `gh` becomes available later, swap
   to real PR URLs.

6. **Re-render both artifacts** with the corrected data and re-deliver
   via `SendUserFile`. The Python render script in this session's bash
   history is the working scaffold — see *Rendering script* below.

## Atlassian MCP auth

State observed at end of session: the MCP server `dcd4c908-…` is
installed but only the `authenticate` and `complete_authentication`
stubs are exposed. The real Jira/Confluence tools (e.g.
`searchJiraIssuesUsingJql`, `getJiraIssue`, `getConfluencePage`) are not
loaded. The `authenticate` tool returns:

> Failed to start OAuth flow: SDK auth failed: You have exceeded the
> rate limit for client registration requests. Ask the user to run /mcp
> and authenticate manually.

**To unblock in a fresh session:**

1. Run `/mcp` and check the Atlassian server status.
2. If listed as un-authenticated, trigger auth from there and complete
   the OAuth flow in the browser.
3. Confirm in `/mcp` that it shows as **connected** (not "waiting").
4. The tool list should then include `mcp__dcd4c908-…__searchJiraIssuesUsingJql`, `__getJiraIssue`, `__getAccessibleAtlassianResources`, `__getConfluencePage`, etc.
5. The Atlassian cloud ID for outsystemsrd was
   `3755dbe1-fa22-4c37-956e-59bea84af9cf` — useful for the first call.

## Skill bugs to fix (separate from the resume work)

Found during the dryrun, **not yet fixed** in the skill:

| Bug | Where | Fix |
|---|---|---|
| Sprint field documented as `customfield_10010` but real ID on OutSystems Jira is `customfield_10006`. | `SKILL.md` lines ~73, 81, 146, 526; `reference/data-sources.md` lines ~13, 16, 69 | Replace `_10010` with `_10006` in all narrative text. Step 2's fields list (SKILL.md:99-100) is already correct. Keep the "if it's missing, try `.fields.sprint`" fallback note. |

These were flagged during the dryrun but no commit yet — they need their
own focused commit.

## Sprint we were processing

| Field | Value |
|---|---|
| Project | RDUCH (Unification Charlie) |
| Sprint name | `RDUCH - RDUCH - 26.Q2.4` |
| Sprint ID | 26356 |
| Board ID | 7404 |
| State | active |
| Dates | 2026-05-11 → 2026-05-22 |
| Goal | "1 — Multi-Infras → Data Fabric Inner-Sourcing Done · 1 — LT Private Connectivity" |
| Snapshot taken | 2026-05-21 (mid-sprint, one day before close) |

### Metrics computed in the dryrun (may shift after re-query)

| Metric | Value |
|---|---|
| Items in sprint | 30 |
| Status mix | 15 Done · 5 In Progress · 5 To Do · 2 In Testing · 1 Blocked · 1 In Code Review · 1 In Peer Review |
| Sized SP | 96 |
| Completed SP | 50 |
| Carryover SP | 46 |
| Unsized items | 3 (RDUCH-178, RDUCH-162, RDUCH-89) |
| Bugs found in sprint | 0 |
| Velocity (this sprint) | 50 SP |
| Avg velocity (prior 3) | 31 SP (Q2.1 47, Q2.2 33, Q2.3 13 — Q2.3 likely under-counted, see #2 above) |
| Goal outcome verdict | Partially achieved (in progress) |

### Heuristic epic groups used (will be replaced by real parent Epic on re-run)

| Epic / workstream (heuristic) | Done / Total | Delivery |
|---|---|---|
| Multi-Infra — Data Fabric Inner-Sourcing | 8 / 12 | 67% |
| LT Connectivity (RQ01 / RQ02 / Discovery) | 5 / 12 | 42% |
| O11 Bridge — maintenance & hardening | 1 / 1 | 100% |
| Self-Host ODC | 1 / 4 | 25% |
| O11 Portfolios | 0 / 1 | — (no Done items — invisible on Delivered slide) |

## Cached data (will need re-fetching)

The dryrun cached two pieces of raw data:

- `/tmp/sprint-issues.json` — slim view (30 items, no parent/Epic Link)
  derived from `mcp-…-searchJiraIssuesUsingJql-1779376918330.txt`.
- `/tmp/closed-issues.json` — slim view of Done items in closed sprints
  for the velocity history (62 items, but attribution to the right
  sprint is imperfect — see #2 above).

Both are in `/tmp/` and **will not survive a session restart** (ephemeral
container). Re-run the queries fresh; don't try to use these.

## Rendering script

The Python script that renders the deck from the cached JSON is in
the bash history of this session, not committed. It substitutes
placeholders into `reference/presentation-template.html` and writes to
`sprint-review-rduch-26q2-4.html`. After MCP auth lands, prefer to:

1. Re-query Jira through the MCP.
2. Build the same Python dict-of-substitutions (placeholders documented
   in `SKILL.md` Step 7).
3. Substitute and write to `sprint-review-rduch-26q2-4.{md,html}` in the
   working directory.
4. `SendUserFile` both files.

The placeholder set in the template right now is:
`DECK_TITLE, TEAM_NAME, SPRINT_DATES, SPRINT_GOAL, SPRINT_GOAL_SHORT,
GOAL_OUTCOME, GOAL_OUTCOME_CLASS, GOAL_OUTCOME_REASON, COMMITTED_SP,
COMPLETED_SP, COMPLETION_PCT, VELOCITY, AVG_VELOCITY, CARRYOVER_SP,
SCOPE_ADDED_SP, BUGS_FOUND, UNSIZED_COUNT, COMMITTED_DONE_SP,
ADDED_DONE_SP, BURNDOWN_JSON, VELOCITY_HISTORY_JSON, KPI_BUCKETS_JSON,
SPRINT_HISTORY_HTML, DEMO_SLIDES_HTML, COMMITTED_DONE_LIST_HTML,
SCOPE_CHANGES_HTML, CARRYOVER_LIST_HTML, NEXT_SPRINT_HTML, SLACK_URL,
CONFLUENCE_URL`.

## Team context (defaults for RDUCH)

- **Slack:** `#unification-charlie` — https://outsystems.enterprise.slack.com/archives/C0ABRM13LLS
- **Confluence team page:** ID `5852397579` — https://outsystemsrd.atlassian.net/wiki/spaces/RDO11PC/pages/5852397579/Unification+Charlie+Team

These are already baked into the SKILL.md and the rendered artifacts.

## Suggested first three messages to a fresh Claude

1. "Read `SESSION-RESUME.md`."
2. "Check `/mcp` — confirm the Atlassian server is authenticated; the
   `searchJiraIssuesUsingJql` tool should be available."
3. "Re-pull RDUCH 26.Q2.4 per the *Pending work* list and re-render both
   artifacts."
