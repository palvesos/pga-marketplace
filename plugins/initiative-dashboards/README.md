# initiative-dashboards

Tooling for Engineering Managers and Product Managers to summarise the progress of an initiative or epic into a self-contained HTML dashboard.

## What it does

Given a single Jira epic or initiative key, the `building-initiative-dashboard` skill:

1. Walks the Jira hierarchy (epic + children + linked epics + cross-team work)
2. Looks up linked GitHub PRs and their CI/review state
3. Optionally pulls Productboard feature notes, Confluence design/UX page links, and a Google Sheets roadmap row
4. Synthesises an **executive Progress Summary** (RAG per track) and **Recommended Actions**
5. Renders an interactive single-file HTML dashboard (KPIs, status doughnut, SP-by-track stacked bar, filterable/sortable item table) and opens it in the browser

## Skill

| Skill | Description |
|---|---|
| [`building-initiative-dashboard`](skills/building-initiative-dashboard) | Build a self-contained progress dashboard for an initiative or epic |

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
