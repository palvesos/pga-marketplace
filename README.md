# pga-marketplace

Paulo Alves' personal Claude Code marketplace — Engineering Manager tooling for OutSystems R&D.

## Plugins

| Plugin | Description |
|---|---|
| [initiative-dashboards](plugins/initiative-dashboards) | Turn a Jira epic key (or a list of them) into self-contained executive HTML dashboards — single-initiative report and portfolio rollup. |

## Installing

In Claude Code:

```
/plugin marketplace add palvesos/pga-marketplace
/plugin install initiative-dashboards@pga-marketplace
```

After install, both skills auto-activate on the trigger phrases below.

---

## Skills & trigger phrases

The plugin ships two skills. They auto-load based on what you ask. Click the skill name for full docs.

### [`building-initiative-dashboard`](plugins/initiative-dashboards/skills/building-initiative-dashboard) — single initiative report

Use one of these phrasings:

- *"build a dashboard for RDUCH-169"*
- *"create a progress dashboard for epic ABC-123"*
- *"make a status dashboard for RDUCH-151"*
- *"executive report for initiative PU-M4.13.1"*
- *"visualise progress on epic RDUCH-200"*
- *"generate an executive update for this epic — RDUCH-199"*

Produces a single `dashboard.html` with KPIs, status doughnut, SP-by-track stacked bar, an executive Progress Summary, Recommended Actions, and a filterable/sortable items table.

### [`building-portfolio-dashboard`](plugins/initiative-dashboards/skills/building-portfolio-dashboard) — rollup across multiple initiatives

Use one of these phrasings:

- *"build a portfolio dashboard for RDUCH-151, RDUCH-169, RDUCH-41"*
- *"rollup status for these initiatives: ABC-100, ABC-200"*
- *"executive rollup for value milestone RPOR-28633"*
- *"VM status dashboard for PU-M2.1.10"*
- *"summary across multiple initiatives"*
- *"build me a status report covering 3 epics — the LT Connectivity one and the two Self-Hosted ones"*

Accepts either a **comma-separated list of Jira keys** or a **single Value Milestone key** (auto-discovers child initiatives). Drills down into each via `building-initiative-dashboard`, then renders a portfolio rollup with:

- Portfolio KPI strip (Green / Yellow / Red counts, SP totals, open PRs)
- **Portfolio Executive Status** (Engineering Director voice, ≤80 words)
- **Portfolio Highlights / Lowlights** (3 each, lowlights must be actionable — Blocker / Pending decision / Pending design / Stalled)
- **Initiatives Index** table — filter by Owner Team and Parent RPOR; click any row to focus
- **Gantt timeline** below the table — Target Start → Target Due bars with GA/EAP markers and a "today" line
- **Selected initiative detail panel** — click a row to see that initiative's RAG light + Exec Status + Highlights/Lowlights
- Per-initiative `dashboard-<KEY>.html` files for drill-down

### Routing

If you ask for a single-initiative report, only `building-initiative-dashboard` activates. If you mention multiple keys, a VM, "rollup", or "portfolio", only `building-portfolio-dashboard` activates and calls the single-initiative one per item.

---

## Prerequisites

**Required:**

- [`acli`](https://developer.atlassian.com/cloud/acli/) — Atlassian CLI authenticated against your Jira instance
- [`gh`](https://cli.github.com/) — GitHub CLI authenticated

**Optional** (skills skip these sources gracefully if not configured):

- Productboard token in `~/.config/outsystems-cli/config.json` (`productboard.auth.token`)
- `prodeng-drive-cli` auth for the roadmap sheet (subject to org Google OAuth policy)
- Confluence access via `koda tool confluence`

---

## Testing

The repo ships two layers of tests for the dashboard skills:

### Skill activation + effectiveness (YAML)

Under `tests/skills/<skill-name>/`:

- `activation.yml` — checks that the right skill activates for given user phrasings.
- `effectiveness.yml` — runs the skill against fixture data in `tests/fixtures/dashboards/` and validates the rendered output.

These are consumed by Anthropic's skill-evaluation harness.

### Incremental-fetch unit tests (Python)

The `building-initiative-dashboard` skill ships with an incremental Jira fetch path (SKILL.md Step 1.5) that diffs against a prior snapshot to cut API calls. Three standalone scripts validate the merge algorithm without touching real Jira or GitHub:

```bash
cd tests/skills/building-initiative-dashboard/incremental-merge
python3 test_merge.py     # merge result must equal a full walk
python3 test_removal.py   # items removed from scope are dropped
python3 test_savings.py   # API-call reduction on a 50-item synthetic case
```

Each script exits non-zero on failure. Inputs live under the same directory's `fixtures/`:

- `fixtures/prior_snapshot.md` — a state snapshot in the schema documented in SKILL.md Step 7.
- `fixtures/current_state.json` — a simulated Jira current state with synthetic `updated` timestamps that drive the JQL filters.

No external dependencies — pure Python 3 standard library. Re-run after any change to Step 1.5's merge logic or the Step 7 schema.

---

## Tested with

OutSystems R&D Jira projects (`RDUCH`, `RDUCO`, `RPOR`) and the OutSystems GitHub org. Other Jira / GitHub instances should work — only the custom field IDs (Story Points = `customfield_10004`, Dev info = `customfield_12600`, parent-RPOR dates = `customfield_15485/15486/15491`) might need adjustment in the SKILL.md.
