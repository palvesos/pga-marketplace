# initiative-dashboards

Tooling for Engineering Managers and Product Managers to summarise the progress of an initiative or epic into a self-contained HTML dashboard.

## What it does

Given a single Jira epic or initiative key, the `building-initiative-dashboard` skill:

1. Walks the Jira hierarchy (epic + children + linked epics + cross-team work)
2. Looks up linked GitHub PRs and their CI/review state
3. Optionally pulls Productboard feature notes, Confluence design/UX page links, and a Google Sheets roadmap row
4. Synthesises an **executive Progress Summary** (RAG per track) and **Recommended Actions**
5. Renders an interactive single-file HTML dashboard (KPIs, status doughnut, SP-by-track stacked bar, filterable/sortable item table) and opens it in the browser

## Skills

| Skill | Description |
|---|---|
| [`building-initiative-dashboard`](skills/building-initiative-dashboard) | Build a self-contained progress dashboard for one initiative or epic |
| [`building-portfolio-dashboard`](skills/building-portfolio-dashboard) | Roll up status across multiple initiatives or a Value Milestone — drills down via `building-initiative-dashboard` per item and renders an executive rollup with portfolio KPIs, Highlights/Lowlights, filterable Initiatives Index, Gantt timeline, and a click-to-show detail panel |

## Claude Desktop bridge

For viewing dashboards as live artifacts in Claude Desktop and scheduling daily metric refreshes, see [`desktop-bridge/`](desktop-bridge) — a small local MCP server + headless refresh script that reads the same `~/initiative-dashboards/<slug>/` snapshots the skill writes.

## Trigger phrases

### `building-initiative-dashboard` (single initiative)

- *"build a dashboard for RDUCH-169"*
- *"create a progress dashboard for epic ABC-123"*
- *"make a status dashboard for RDUCH-151"*
- *"executive report for initiative PU-M4.13.1"*
- *"visualise progress on epic RDUCH-200"*
- *"generate an executive update for this epic — RDUCH-199"*

### `building-portfolio-dashboard` (rollup)

- *"build a portfolio dashboard for RDUCH-151, RDUCH-169, RDUCH-41"*
- *"rollup status for these initiatives: ABC-100, ABC-200"*
- *"executive rollup for value milestone RPOR-28633"*
- *"VM status dashboard for PU-M2.1.10"*
- *"summary across multiple initiatives"*
- *"build me a status report covering 3 epics — the LT Connectivity one and the two Self-Hosted ones"*

Accepts either a comma-separated list of Jira keys, or a single Value Milestone key (auto-discovers child initiatives).

## Prerequisites

Required:

- `acli` — Atlassian CLI authenticated against your Jira instance
- `gh` — GitHub CLI authenticated

Optional (skill skips gracefully if absent):

- Productboard token in `~/.config/outsystems-cli/config.json` (`productboard.auth.token`)
- `prodeng-drive-cli` auth for the roadmap sheet
- Confluence access via `koda tool confluence`

## Tested with

OutSystems R&D Jira projects (`RDUCH`, `RDUCO`, `RPOR`) and the OutSystems GitHub org. Other Jira / GitHub instances should work — only the custom field IDs (Story Points = `customfield_10004`, Dev info = `customfield_12600`) might need adjustment.
