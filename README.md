# pga-marketplace

Paulo Alves' personal Claude Code marketplace — Engineering Manager tooling for OutSystems R&D.

## Plugins

| Plugin | Description |
|---|---|
| [initiative-dashboards](plugins/initiative-dashboards) | Turn a Jira epic key (or a list of them) into self-contained executive HTML dashboards — and into live, daily-refreshed artifacts inside Claude Desktop. |

---

## Two usage patterns

The same `~/initiative-dashboards/<slug>/` snapshot folder backs both flows — pick either, or use them together.

### Pattern A — Claude Code (one-shot HTML report)

Best when you want a polished executive report with fresh narrative to share over Slack / email. Each run does the full Jira/GitHub walk, the LLM authors the narrative blocks (Executive Status, Highlights/Lowlights, Progress Summary, Recommended Actions), and a self-contained `dashboard.html` lands in the initiative folder.

**Trigger:** in any Claude Code session, *"build a dashboard for RDUCH-169"*.

See [Skills & trigger phrases](#skills--trigger-phrases-pattern-a) below.

### Pattern B — Claude Desktop (live artifact + daily refresh)

Best for ongoing tracking — KPIs refresh automatically every morning via a Claude Desktop scheduled task, and you view the dashboard inline as a React artifact whenever you open a chat. No LLM cost on the daily run; the narrative carries over from your last Pattern-A run until you regenerate it.

**Trigger:** in any Claude Desktop chat, *"show the latest RDUCH-169 snapshot as an interactive artifact"*.

See [Claude Desktop bridge](#claude-desktop-bridge-pattern-b) below.

---

## Installing

### For Pattern A (Claude Code skill)

```
/plugin marketplace add palvesos/pga-marketplace
/plugin install initiative-dashboards@pga-marketplace
```

Both skills auto-activate on the trigger phrases listed below.

### For Pattern B (Claude Desktop MCP bridge)

```bash
git clone https://github.com/palvesos/pga-marketplace.git
cd pga-marketplace/plugins/initiative-dashboards/desktop-bridge
pip install -e .
```

Then merge this into `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "initiative-dashboards": {
      "command": "python3",
      "args": [
        "/ABSOLUTE/PATH/TO/pga-marketplace/plugins/initiative-dashboards/desktop-bridge/mcp_server.py"
      ]
    }
  }
}
```

Replace `/ABSOLUTE/PATH/TO/...` with your real path. If `python3` in your config doesn't have the `mcp` SDK installed, replace `"python3"` with the absolute path to the python where `pip install -e .` succeeded — check with `which python3` from that shell.

Restart Claude Desktop. In **Settings → Developer** you should see `initiative-dashboards` with 4 tools (`refresh_snapshot`, `get_latest_snapshot`, `list_snapshots`, `get_snapshot_history`).

Full bridge docs (tool reference, troubleshooting, file layout): [`plugins/initiative-dashboards/desktop-bridge/README.md`](plugins/initiative-dashboards/desktop-bridge/README.md).

---

## Skills & trigger phrases (Pattern A)

The plugin ships two skills. They auto-load based on what you ask. Click the skill name for full docs.

### [`building-initiative-dashboard`](plugins/initiative-dashboards/skills/building-initiative-dashboard) — single initiative report

Use one of these phrasings:

- *"build a dashboard for RDUCH-169"*
- *"create a progress dashboard for epic ABC-123"*
- *"make a status dashboard for RDUCH-151"*
- *"executive report for initiative PU-M4.13.1"*
- *"visualise progress on epic RDUCH-200"*
- *"generate an executive update for this epic — RDUCH-199"*

Produces a single timestamped `<slug>__<ts>.html` and matching state `<slug>__<ts>.md` under `~/initiative-dashboards/<slug>/` (override base dir via `$INITIATIVE_DASHBOARDS_DIR`). Snapshots are append-only so you can compare progress across dates.

### [`building-portfolio-dashboard`](plugins/initiative-dashboards/skills/building-portfolio-dashboard) — rollup across multiple initiatives

Use one of these phrasings:

- *"build a portfolio dashboard for RDUCH-151, RDUCH-169, RDUCH-41"*
- *"rollup status for these initiatives: ABC-100, ABC-200"*
- *"executive rollup for value milestone RPOR-28633"*
- *"VM status dashboard for PU-M2.1.10"*
- *"summary across multiple initiatives"*

Accepts a comma-separated list of Jira keys or a single Value Milestone key (auto-discovers child initiatives). Drills down via `building-initiative-dashboard`, then renders a portfolio rollup with Portfolio KPI strip, Executive Status, Highlights/Lowlights, filterable Initiatives Index, Gantt timeline, and a click-to-show detail panel.

### Routing

Single-initiative request → only `building-initiative-dashboard` activates. Multiple keys / VM / "rollup" / "portfolio" → only `building-portfolio-dashboard` activates and calls the single-initiative skill per item.

---

## Claude Desktop bridge (Pattern B)

After the install steps above, three things work in any Claude Desktop chat:

> *"List my initiative snapshots"* — calls `list_snapshots`, shows everything on disk.

> *"Update snapshot from RDUCH-169"* — calls `refresh_snapshot(mode="metrics")`, runs headless `acli` + `gh`, writes a new timestamped `.md`. No LLM authoring; narrative carries over from the prior snapshot.

> *"Show the latest RDUCH-169 snapshot as an interactive artifact with KPIs, status counts, and the items table"* — Claude reads `get_latest_snapshot` and renders a React + Chart.js artifact inline.

### Setting up the daily refresh task

Claude Desktop's built-in **Tasks** feature is the scheduler — no cron or launchd required.

1. In Claude Desktop: **Tasks** → **New Task**.
2. **Schedule:** Daily at the time you want (e.g. 08:00 before standup).
3. **Prompt:**

   > Update snapshots for RDUCH-169, RDUCH-200, and PU-M4.13.1. Call `refresh_snapshot` with `mode="metrics"` for each. Reply with a one-line summary of any RAG changes since yesterday.

Tomorrow morning you'll get a Tasks notification with the summary. The new snapshots will be on disk; the artifact in any open chat re-fetches them automatically.

### Refresh modes

| Mode | Trigger | Cost | What changes |
|---|---|---|---|
| **Metrics refresh** | Scheduled task or *"update snapshot from RDUCH-169"* in chat | Free (just `acli`/`gh`) | KPIs, status counts, items, tracks, deltas. Narrative carried over. |
| **Full LLM report** | *"Regenerate the full RDUCH-169 dashboard"* in chat — Claude calls `refresh_snapshot` for fresh data, then re-authors every narrative block per the skill's Step 5 rules. | Anthropic API credit | All narrative blocks (Executive Status, Highlights/Lowlights, Progress Summary, Recommended Actions). |

Daily metrics + weekly full report is the sensible cadence for most teams.

---

## Prerequisites

**Required (both patterns):**

- [`acli`](https://developer.atlassian.com/cloud/acli/) — Atlassian CLI authenticated against your Jira instance
- [`gh`](https://cli.github.com/) — GitHub CLI authenticated

**For Pattern B only:**

- Python 3.10+
- Claude Desktop installed

**Optional** (skills skip these sources gracefully if not configured):

- Productboard token in `~/.config/outsystems-cli/config.json` (`productboard.auth.token`)
- `prodeng-drive-cli` auth for the roadmap sheet
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

Each script exits non-zero on failure. Pure Python 3 stdlib, no deps. Re-run after any change to Step 1.5's merge logic or the Step 7 schema.

---

## Tested with

OutSystems R&D Jira projects (`RDUCH`, `RDUCO`, `RPOR`) and the OutSystems GitHub org. Other Jira / GitHub instances should work — only the custom field IDs (Story Points = `customfield_10004`, Dev info = `customfield_12600`, parent-RPOR dates = `customfield_15485/15486/15491`) might need adjustment in the SKILL.md and/or `refresh.py`.
