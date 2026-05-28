# desktop-bridge

Local glue that lets Claude Desktop view and refresh the initiative dashboards produced by the [`building-initiative-dashboard`](../skills/building-initiative-dashboard) skill — including from a Claude Desktop scheduled task.

Three pieces, all on your machine, nothing in the cloud:

| File | Role |
|---|---|
| `refresh.py` | Headless data refresh — calls `acli` + `gh`, writes a new `.md` snapshot to `~/initiative-dashboards/<slug>/`. No LLM in the loop. |
| `mcp_server.py` | MCP server Claude Desktop connects to. Exposes `refresh_snapshot`, `get_latest_snapshot`, `list_snapshots`, `get_snapshot_history`. |
| `snapshot.py` | Shared parser/writer for the Step 7 state-snapshot schema. |

## Prerequisites

- macOS or Linux with Python 3.10+
- [`acli`](https://developer.atlassian.com/cloud/acli/) authenticated against your Jira instance
- [`gh`](https://cli.github.com/) authenticated against GitHub
- Claude Desktop installed

## Install

From the repo root:

```bash
cd plugins/initiative-dashboards/desktop-bridge
pip install -e .
```

That installs the `mcp` Python SDK and registers two console scripts:

- `initiative-dashboards-refresh <JIRA_KEY>` — one-shot headless refresh
- `initiative-dashboards-mcp` — runs the MCP server on stdio (Claude Desktop launches this for you)

## Wire into Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows) and merge in:

```jsonc
{
  "mcpServers": {
    "initiative-dashboards": {
      "command": "python3",
      "args": [
        "/ABSOLUTE/PATH/TO/pga-marketplace/plugins/initiative-dashboards/desktop-bridge/mcp_server.py"
      ],
      "env": {
        "INITIATIVE_DASHBOARDS_DIR": "/Users/YOU/initiative-dashboards"
      }
    }
  }
}
```

See `claude_desktop_config.snippet.json` for a copy-pasteable version. Restart Claude Desktop after editing.

## Try it

In a Claude Desktop chat:

> "List my initiative snapshots"

> "Update snapshot from RDUCH-169" — or — "Refresh snapshot for RDUCH-169"

> "Show the latest RDUCH-169 snapshot as an interactive artifact"

The third prompt is where Claude reads the snapshot via `get_latest_snapshot`, generates a React + Chart.js artifact populated with the data, and renders it inline. Each new chat re-fetches the latest snapshot, so reopening the artifact tomorrow shows tomorrow's numbers.

## Schedule a daily refresh

Use Claude Desktop's built-in **Tasks** (Scheduled Prompts) — no cron required.

1. In Claude Desktop, open **Tasks** → **New Task**.
2. **Schedule**: Daily at, say, 08:00.
3. **Prompt**:

   > Update snapshots for RDUCH-169, RDUCH-200, and PU-M4.13.1. Call `refresh_snapshot` with `mode="metrics"` for each. Reply with a one-line summary of any RAG changes since yesterday.

Each scheduled run calls `refresh.py` via the MCP tool, which:

1. Reads the latest existing snapshot (if any) to seed incremental fetching.
2. Issues the three Step 1.5 JQL queries (`updated >= prior_iso`, `created >= prior_iso`, key-only reconcile) against Jira via `acli`.
3. Re-queries `gh search prs` only for items that changed.
4. Writes a new `<slug>__<timestamp>.md` carrying refreshed metrics + the prior snapshot's narrative.
5. Returns the new snapshot JSON to Claude for the one-line summary.

### Refresh modes

| Mode                | Triggered by                                 | Cost           | What changes                     |
|---------------------|----------------------------------------------|----------------|----------------------------------|
| **Metrics refresh** | `refresh_snapshot(..., mode="metrics")` from a scheduled task or chat | Free (just acli/gh) | KPIs, status counts, items, RAG carried over |
| **Full LLM report** | Asking Claude to run the `building-initiative-dashboard` skill end-to-end (via Claude Code, or by asking Claude Desktop to "regenerate the full report"). The LLM authors fresh narrative, then writes via the same MCP tool path. | Anthropic API credit | All narrative blocks re-authored |

The expensive narrative refresh is opt-in — call it weekly, or when you want a fresh executive prose pass before sharing the dashboard with leadership.

## Tools exposed by the MCP server

| Tool | Args | Returns |
|---|---|---|
| `refresh_snapshot` | `jira_key`, `mode` (`"metrics"` \| `"data-only"`), `full_fetch` | New snapshot JSON |
| `get_latest_snapshot` | `jira_key` | Most recent snapshot JSON |
| `list_snapshots` | — | All initiatives with at least one snapshot on disk |
| `get_snapshot_history` | `jira_key`, `limit` (default 10) | Time series of `{snapshot_iso, rag, scope, counts_by_status}` |

The JSON returned by `refresh_snapshot` / `get_latest_snapshot` matches the YAML frontmatter schema documented in SKILL.md Step 7 — so any artifact Claude generates can use the same field names that the skill's HTML template uses.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `refresh.py: 'acli' not found on PATH` | Install Atlassian CLI and ensure it's on PATH for the user that Claude Desktop runs as. |
| MCP server doesn't show up in Claude Desktop | Restart Claude Desktop after editing the config; check `~/Library/Logs/Claude/mcp.log`. |
| `the 'mcp' Python SDK is not installed` | Re-run `pip install -e .` from this directory with the same Python that Claude Desktop's `command` field points at. |
| Refresh writes to the wrong folder | Set `INITIATIVE_DASHBOARDS_DIR` in the MCP server's `env` block. The headless `refresh.py` honours the same env var. |
| `acli` returns rows with unexpected field names | Custom field IDs (Story Points = `customfield_10004`, Dev info = `customfield_12600`) may differ on your Jira instance — adjust in `refresh.py`. |
