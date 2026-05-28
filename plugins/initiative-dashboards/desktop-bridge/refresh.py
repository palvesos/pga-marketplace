"""Headless dashboard refresh — same data model as the SKILL.md skill,
but without the LLM in the loop. Mirrors SKILL.md Steps 1, 1.5, 2, 4.

CLI:
    python3 refresh.py <JIRA_KEY>
    python3 refresh.py <JIRA_KEY> --full-fetch          # skip incremental
    python3 refresh.py <JIRA_KEY> --json                # also emit JSON to stdout

Narrative fields (executive_status, highlights, lowlights, progress_summary,
recommended_actions) are CARRIED OVER from the most recent prior snapshot
if one exists, and left empty otherwise. A separate LLM run is responsible
for refreshing those.

Requires:
    - `acli` on PATH, authenticated against Jira
    - `gh` on PATH, authenticated against GitHub
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from snapshot import (
    Item,
    Snapshot,
    base_dir,
    folder_for,
    latest_snapshot,
    parse_snapshot,
    slug_for,
    snapshot_paths,
    timestamp,
    write_snapshot,
)


IN_FLIGHT_STATUSES = {"In Progress", "In Peer Review", "In Review", "In Testing"}
INCREMENTAL_MAX_AGE_DAYS = 30


# --- subprocess helpers ------------------------------------------------------

def _run(cmd: list[str], check: bool = True) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{proc.stderr}")
    return proc.stdout


def _check_prereqs() -> None:
    for tool in ("acli", "gh"):
        if shutil.which(tool) is None:
            sys.exit(f"refresh.py: {tool!r} not found on PATH — install it and authenticate first.")


# --- Jira fetch --------------------------------------------------------------

def fetch_epic(jira_key: str) -> dict[str, Any]:
    out = _run(["acli", "jira", "workitem", "view", jira_key, "--fields", "*all", "--json"])
    return json.loads(out)


def fetch_children(jira_key: str, since_iso: str | None = None,
                   created_since: bool = False) -> list[dict[str, Any]]:
    jql = f'"Epic Link" = {jira_key} OR parent = {jira_key}'
    if since_iso:
        field = "created" if created_since else "updated"
        jql = f'({jql}) AND {field} >= "{since_iso}"'
    out = _run([
        "acli", "jira", "workitem", "search",
        "--jql", jql,
        "--fields", "key,summary,status,assignee,issuetype,updated,customfield_10004,customfield_12600",
        "--json",
    ])
    return json.loads(out) if out.strip() else []


def fetch_reconcile_keys(jira_key: str) -> set[str]:
    out = _run([
        "acli", "jira", "workitem", "search",
        "--jql", f'"Epic Link" = {jira_key} OR parent = {jira_key}',
        "--fields", "key",
        "--json",
    ])
    rows = json.loads(out) if out.strip() else []
    return {r["key"] for r in rows}


def fetch_linked_epics(jira_key: str) -> list[str]:
    out = _run([
        "acli", "jira", "workitem", "search",
        "--jql", f"issue in linkedIssues({jira_key})",
        "--fields", "key,issuetype",
        "--json",
    ])
    rows = json.loads(out) if out.strip() else []
    return [r["key"] for r in rows if r.get("fields", {}).get("issuetype", {}).get("name") == "Epic"]


# --- Item normalization ------------------------------------------------------

def jira_row_to_item(row: dict[str, Any]) -> Item:
    f = row.get("fields", {})
    assignee = f.get("assignee") or {}
    return Item(
        key=row["key"],
        type=(f.get("issuetype") or {}).get("name"),
        summary=f.get("summary"),
        status=(f.get("status") or {}).get("name"),
        sp=f.get("customfield_10004"),
        track=_classify_track(f.get("summary", ""), row["key"]),
        assignee=assignee.get("emailAddress") or assignee.get("displayName") or "-",
        updated=f.get("updated"),
        pr_url=None, pr_state=None, pr_repo=None,
    )


def _classify_track(summary: str, key: str) -> str:
    """Best-effort track classification — same heuristic the skill uses.
    Looks for [RQXX] tag in summary, else falls back to the project prefix."""
    import re
    m = re.search(r"\[(RQ\d+|RDQ\d+|M\d+)\]", summary or "")
    if m:
        return m.group(1)
    project = key.split("-", 1)[0]
    return project


# --- GitHub PR fetch ---------------------------------------------------------

def fetch_prs_for_item(jira_key: str) -> tuple[str | None, str | None, str | None]:
    """Returns (pr_url, pr_state, pr_repo) — picks the most relevant single PR."""
    candidates: list[dict[str, Any]] = []
    for state_flag in ([], ["--state", "closed"]):
        try:
            out = _run([
                "gh", "search", "prs", jira_key,
                "--limit", "5",
                "--json", "url,title,state,repository,isDraft",
                *state_flag,
            ], check=False)
            candidates.extend(json.loads(out) if out.strip() else [])
        except Exception:
            continue
    if not candidates:
        return None, None, None
    # Prefer open over closed; merged over closed-not-merged
    def rank(pr: dict[str, Any]) -> int:
        state = pr.get("state", "").upper()
        if state == "OPEN":
            return 0
        if "MERGED" in pr.get("title", "").upper() or state == "MERGED":
            return 1
        return 2
    candidates.sort(key=rank)
    chosen = candidates[0]
    repo = chosen.get("repository", {}).get("nameWithOwner") or ""
    return chosen.get("url"), chosen.get("state", "").upper(), repo


# --- Rollup ------------------------------------------------------------------

def compute_scope(items: list[Item]) -> dict[str, int]:
    sp_done = sum((i.sp or 0) for i in items if i.status == "Done")
    sp_in_flight = sum((i.sp or 0) for i in items if i.status in IN_FLIGHT_STATUSES)
    sp_todo = sum((i.sp or 0) for i in items if i.status == "To Do" and i.sp is not None)
    unsized = sum(1 for i in items if i.sp is None)
    open_prs = sum(1 for i in items if i.pr_state == "OPEN")
    return {
        "sp_total_sized": sp_done + sp_in_flight + sp_todo,
        "sp_done": sp_done,
        "sp_in_flight": sp_in_flight,
        "sp_todo_sized": sp_todo,
        "items_unsized": unsized,
        "items_total": len(items),
        "open_prs": open_prs,
    }


def compute_tracks(items: list[Item]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for it in items:
        d = out.setdefault(it.track or "(none)", {"sp_done": 0, "sp_in_flight": 0, "sp_todo": 0})
        sp = it.sp or 0
        if it.status == "Done":
            d["sp_done"] += sp
        elif it.status in IN_FLIGHT_STATUSES:
            d["sp_in_flight"] += sp
        elif it.status == "To Do" and it.sp is not None:
            d["sp_todo"] += sp
    for d in out.values():
        total = d["sp_done"] + d["sp_in_flight"] + d["sp_todo"]
        if total == 0:
            d["rag"] = "yellow"
        elif d["sp_done"] / total >= 0.5:
            d["rag"] = "green"
        elif d["sp_in_flight"] > 0:
            d["rag"] = "yellow"
        else:
            d["rag"] = "red"
    return out


# --- Refresh entry point -----------------------------------------------------

def refresh(jira_key: str, *, full_fetch: bool = False) -> Path:
    _check_prereqs()

    prior_md = latest_snapshot(jira_key)
    prior: Snapshot | None = None
    fetch_mode = "full"
    if prior_md and not full_fetch:
        try:
            prior = parse_snapshot(prior_md)
            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(
                prior.snapshot_iso.replace("Z", "+00:00")
            )).days
            if age_days <= INCREMENTAL_MAX_AGE_DAYS:
                fetch_mode = "incremental"
        except Exception as e:
            print(f"warning: prior snapshot {prior_md.name} unreadable ({e}), falling back to full walk", file=sys.stderr)

    # Resolve items
    if fetch_mode == "incremental":
        prior_iso = prior.snapshot_iso  # type: ignore[union-attr]
        prior_items = {i.key: i for i in prior.items}  # type: ignore[union-attr]

        changed_rows = fetch_children(jira_key, since_iso=prior_iso)
        added_rows = fetch_children(jira_key, since_iso=prior_iso, created_since=True)
        keys_in_scope = fetch_reconcile_keys(jira_key)

        working: dict[str, Item] = dict(prior_items)
        for row in changed_rows + added_rows:
            it = jira_row_to_item(row)
            working[it.key] = it

        # Drop items no longer in scope
        for k in list(working):
            if k not in keys_in_scope:
                del working[k]

        items = list(working.values())

        # Re-fetch PRs only for items in the changed/added set
        changed_keys = {row["key"] for row in changed_rows + added_rows}
        for it in items:
            if it.key in changed_keys:
                it.pr_url, it.pr_state, it.pr_repo = fetch_prs_for_item(it.key)

        linked_epics = prior.linked_epics  # type: ignore[union-attr]

    else:
        rows = fetch_children(jira_key)
        items = [jira_row_to_item(r) for r in rows]
        for it in items:
            it.pr_url, it.pr_state, it.pr_repo = fetch_prs_for_item(it.key)
        linked_epics = fetch_linked_epics(jira_key)

    # Header data
    epic = fetch_epic(jira_key)
    title = (epic.get("fields", {}).get("summary")
             or (prior.initiative_title if prior else jira_key))

    now = datetime.now(timezone.utc)
    snap_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    snap_date = now.strftime("%Y-%m-%d")
    ts = timestamp(datetime.now())

    md_path, html_path = snapshot_paths(jira_key, ts)

    snap = Snapshot(
        initiative_key=jira_key,
        initiative_title=title,
        snapshot_iso=snap_iso,
        snapshot_date=snap_date,
        html_file=html_path.name,
        previous_snapshot=prior_md.name if prior_md else None,
        fetch_mode=fetch_mode,
        rag=(prior.rag if prior else {"status": "yellow", "label": "Refresh pending", "headline": "Metrics refreshed; narrative awaiting LLM update."}),
        scope=compute_scope(items),
        counts_by_status=dict(Counter(i.status for i in items if i.status)),
        tracks=compute_tracks(items),
        linked_epics=linked_epics,
        items=items,
        sources_queried=["Jira", "GitHub"],
        # Carry over the narrative from the prior snapshot — LLM refresh
        # is responsible for updating these.
        narrative=(prior.narrative if prior else {}),
    )

    write_snapshot(snap, md_path)
    return md_path


# --- CLI ---------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jira_key", help="Jira epic / initiative key, e.g. RDUCH-169")
    ap.add_argument("--full-fetch", action="store_true",
                    help="Skip incremental mode and re-walk the full tree.")
    ap.add_argument("--json", action="store_true",
                    help="Emit the new snapshot as JSON on stdout after writing.")
    args = ap.parse_args()

    path = refresh(args.jira_key, full_fetch=args.full_fetch)
    print(f"wrote {path}", file=sys.stderr)
    if args.json:
        snap = parse_snapshot(path)
        json.dump(snap.to_json(), sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
