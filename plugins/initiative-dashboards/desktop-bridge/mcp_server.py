"""MCP server bridging local snapshot files to Claude Desktop.

Exposes four tools:
    refresh_dashboard(jira_key, mode="metrics")
        mode="metrics" -> headless refresh.py run (no LLM)
        mode="data-only" -> read latest snapshot without re-fetching
    get_latest_dashboard(jira_key)
        Returns the latest snapshot for the given initiative as JSON.
    list_initiatives()
        Returns all initiatives that have at least one snapshot on disk.
    get_snapshot_history(jira_key, limit=10)
        Returns the last <limit> snapshots' metadata + scope KPIs (for trends).

Install:
    pip install "mcp[cli]"

Wire into Claude Desktop by adding to ~/Library/Application Support/Claude/
claude_desktop_config.json — see desktop-bridge/README.md for the snippet.

Run standalone for debugging:
    python3 mcp_server.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make sibling modules importable when launched by path from Claude Desktop.
sys.path.insert(0, str(Path(__file__).parent))

from snapshot import (
    Snapshot,
    base_dir,
    folder_for,
    latest_snapshot,
    list_snapshots,
    parse_snapshot,
    slug_for,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.exit(
        "mcp_server.py: the `mcp` Python SDK is not installed.\n"
        "Run: pip install \"mcp[cli]\"\n"
        "See: https://modelcontextprotocol.io/quickstart"
    )

import refresh as refresh_module

mcp = FastMCP("initiative-dashboards")


def _snap_to_json(snap: Snapshot) -> dict:
    return snap.to_json()


@mcp.tool()
def refresh_dashboard(jira_key: str, mode: str = "metrics", full_fetch: bool = False) -> dict:
    """Refresh the metrics for a Jira initiative or epic.

    Args:
        jira_key: e.g. "RDUCH-169" — the Jira key for the initiative.
        mode: "metrics" runs a headless refresh (acli + gh, no LLM, fast and free).
              "data-only" just reads the latest existing snapshot and returns it
              without re-fetching anything.
        full_fetch: when true, force a full walk instead of incremental mode.

    Returns:
        The new snapshot as a JSON dict (frontmatter shape from SKILL.md Step 7).
    """
    if mode == "data-only":
        latest = latest_snapshot(jira_key)
        if latest is None:
            return {"error": f"no snapshot on disk for {jira_key}"}
        return _snap_to_json(parse_snapshot(latest))

    if mode != "metrics":
        return {"error": f"unsupported mode {mode!r} — use 'metrics' or 'data-only'"}

    try:
        md_path = refresh_module.refresh(jira_key, full_fetch=full_fetch)
    except RuntimeError as e:
        return {"error": str(e)}
    snap = parse_snapshot(md_path)
    payload = _snap_to_json(snap)
    payload["_snapshot_path"] = str(md_path)
    return payload


@mcp.tool()
def get_latest_dashboard(jira_key: str) -> dict:
    """Return the most recent snapshot for an initiative.

    Useful when an artifact or chat just wants to display today's data without
    triggering a fresh acli/gh fetch.
    """
    latest = latest_snapshot(jira_key)
    if latest is None:
        return {"error": f"no snapshot on disk for {jira_key}"}
    return _snap_to_json(parse_snapshot(latest))


@mcp.tool()
def list_initiatives() -> dict:
    """List all initiatives that currently have at least one snapshot on disk."""
    base = base_dir()
    if not base.is_dir():
        return {"base_dir": str(base), "initiatives": []}
    initiatives = []
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        snaps = sorted(d.glob("*.md"))
        if not snaps:
            continue
        try:
            latest = parse_snapshot(snaps[-1])
        except Exception:
            continue
        initiatives.append({
            "slug": d.name,
            "key": latest.initiative_key,
            "title": latest.initiative_title,
            "latest_snapshot_iso": latest.snapshot_iso,
            "snapshot_count": len(snaps),
        })
    return {"base_dir": str(base), "initiatives": initiatives}


@mcp.tool()
def get_snapshot_history(jira_key: str, limit: int = 10) -> dict:
    """Return KPI-level history for an initiative — useful for trend rendering.

    Each entry includes snapshot_iso, RAG, and the `scope` block (SP done /
    in-flight / to-do / unsized / open-PRs). Narrative bullets are omitted
    to keep the payload light.
    """
    snaps = list_snapshots(jira_key)[:limit]
    if not snaps:
        return {"key": jira_key, "history": []}
    history = []
    for p in reversed(snaps):  # oldest -> newest for chart-friendly order
        try:
            s = parse_snapshot(p)
        except Exception:
            continue
        history.append({
            "snapshot_iso": s.snapshot_iso,
            "snapshot_date": s.snapshot_date,
            "fetch_mode": s.fetch_mode,
            "rag": s.rag,
            "scope": s.scope,
            "counts_by_status": s.counts_by_status,
            "file": p.name,
        })
    return {"key": jira_key, "history": history}


if __name__ == "__main__":
    mcp.run()
