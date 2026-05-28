"""Read/write helpers for initiative-dashboard state snapshots.

Each snapshot lives at:
    <base>/<slug>/<slug>__<YYYY_MM_DD_HH_MM_SS>.md

The schema is defined in plugins/initiative-dashboards/skills/
building-initiative-dashboard/SKILL.md (Step 7). This module provides
just enough parsing/writing for the headless refresh and MCP server to
roundtrip snapshots without depending on PyYAML.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


# --- Paths and naming --------------------------------------------------------

def base_dir() -> Path:
    """Honour $INITIATIVE_DASHBOARDS_DIR, else ~/initiative-dashboards/."""
    override = os.environ.get("INITIATIVE_DASHBOARDS_DIR")
    return Path(override).expanduser() if override else Path.home() / "initiative-dashboards"


def slug_for(jira_key: str) -> str:
    """RDUCH-169 -> rduch_169, PU-M4.13.1 -> pu_m4_13_1."""
    s = re.sub(r"[^a-z0-9]+", "_", jira_key.lower())
    return re.sub(r"_+", "_", s).strip("_")


def folder_for(jira_key: str) -> Path:
    return base_dir() / slug_for(jira_key)


def timestamp(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y_%m_%d_%H_%M_%S")


def snapshot_paths(jira_key: str, ts: str | None = None) -> tuple[Path, Path]:
    """Returns (md_path, html_path) for a new snapshot."""
    slug = slug_for(jira_key)
    ts = ts or timestamp()
    folder = base_dir() / slug
    return folder / f"{slug}__{ts}.md", folder / f"{slug}__{ts}.html"


def list_snapshots(jira_key: str) -> list[Path]:
    """Newest first. Empty list if folder doesn't exist."""
    folder = folder_for(jira_key)
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.md"), key=lambda p: p.name, reverse=True)


def latest_snapshot(jira_key: str) -> Path | None:
    snaps = list_snapshots(jira_key)
    return snaps[0] if snaps else None


# --- Snapshot data model -----------------------------------------------------

@dataclass
class Item:
    key: str
    type: str | None = None
    summary: str | None = None
    status: str | None = None
    sp: int | None = None
    track: str | None = None
    assignee: str | None = None
    updated: str | None = None
    pr_url: str | None = None
    pr_state: str | None = None
    pr_repo: str | None = None


@dataclass
class Snapshot:
    initiative_key: str
    initiative_title: str
    snapshot_iso: str
    snapshot_date: str
    html_file: str | None = None
    previous_snapshot: str | None = None
    fetch_mode: str = "full"
    rag: dict[str, str] = field(default_factory=lambda: {"status": "yellow", "label": "", "headline": ""})
    scope: dict[str, int] = field(default_factory=dict)
    counts_by_status: dict[str, int] = field(default_factory=dict)
    tracks: dict[str, dict[str, Any]] = field(default_factory=dict)
    linked_epics: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    sources_queried: list[str] = field(default_factory=list)
    narrative: dict[str, list[str] | str] = field(default_factory=dict)
    """narrative keys: executive_status[], highlights[], lowlights[],
    progress_summary[], recommended_actions[], delta[]"""

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["items"] = [asdict(i) for i in self.items]
        return d


# --- Parsing -----------------------------------------------------------------

def _coerce(value: str):
    v = value.strip().strip('"').strip("'")
    if v in ("null", "None", ""):
        return None
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    return v


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_snapshot(md_path: Path) -> Snapshot:
    text = md_path.read_text()
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{md_path}: missing YAML frontmatter")
    fm, body = m.group(1), m.group(2)

    def grab(key: str, default=None):
        match = re.search(rf"^{key}:\s*(.*)$", fm, re.MULTILINE)
        return _coerce(match.group(1)) if match else default

    items = _parse_items_block(fm)
    rag = _parse_block(fm, "rag")
    scope = {k: int(v) for k, v in _parse_block(fm, "scope").items() if v not in (None, "")}
    counts = _parse_block(fm, "counts_by_status")
    counts_int = {k: int(v) for k, v in counts.items() if v not in (None, "")}
    tracks = _parse_tracks_block(fm)
    linked = _parse_inline_list(fm, "linked_epics")
    sources = _parse_inline_list(fm, "sources_queried")
    narrative = _parse_narrative_body(body)

    return Snapshot(
        initiative_key=grab("initiative_key"),
        initiative_title=grab("initiative_title"),
        snapshot_iso=grab("snapshot_iso"),
        snapshot_date=grab("snapshot_date"),
        html_file=grab("html_file"),
        previous_snapshot=grab("previous_snapshot"),
        fetch_mode=grab("fetch_mode", "full"),
        rag=rag or {"status": "yellow", "label": "", "headline": ""},
        scope=scope,
        counts_by_status=counts_int,
        tracks=tracks,
        linked_epics=linked,
        items=items,
        sources_queried=sources,
        narrative=narrative,
    )


def _parse_block(fm: str, key: str) -> dict[str, Any]:
    """Parse a simple mapping block like rag: ... or scope: ..."""
    m = re.search(rf"^{key}:\n((?:  .+\n)+)", fm, re.MULTILINE)
    if not m:
        return {}
    out: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        m2 = re.match(r"^  (\w+):\s*(.*)$", line)
        if m2:
            out[m2.group(1)] = _coerce(m2.group(2))
    return out


def _parse_tracks_block(fm: str) -> dict[str, dict[str, Any]]:
    m = re.search(r"^tracks:\n((?:  .+\n)+)", fm, re.MULTILINE)
    if not m:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for line in m.group(1).splitlines():
        # Inline flow: "  RQ01: { rag: green, sp_done: 12, ... }"
        m2 = re.match(r"^\s*(\S+?):\s*\{(.+)\}\s*$", line)
        if m2:
            name = m2.group(1)
            fields = {}
            for chunk in m2.group(2).split(","):
                if ":" in chunk:
                    k, v = chunk.split(":", 1)
                    fields[k.strip()] = _coerce(v)
            out[name] = fields
    return out


def _parse_inline_list(fm: str, key: str) -> list[str]:
    m = re.search(rf"^{key}:\s*\[(.*?)\]\s*$", fm, re.MULTILINE)
    if not m:
        return []
    raw = m.group(1).strip()
    if not raw:
        return []
    return [x.strip().strip('"').strip("'") for x in raw.split(",")]


def _parse_items_block(fm: str) -> list[Item]:
    m = re.search(r"^items:\n((?:  - .+\n(?:    .+\n)*)+)", fm, re.MULTILINE)
    if not m:
        return []
    items: list[Item] = []
    current: dict[str, Any] | None = None
    for line in m.group(1).splitlines():
        if re.match(r"^  - key:\s*", line):
            if current is not None:
                items.append(Item(**current))
            current = {"key": _coerce(line.split(":", 1)[1])}
        else:
            m2 = re.match(r"^    (\w+):\s*(.*)$", line)
            if m2 and current is not None:
                k, v = m2.group(1), _coerce(m2.group(2))
                if k in Item.__dataclass_fields__:
                    current[k] = v
    if current is not None:
        items.append(Item(**current))
    return items


def _parse_narrative_body(body: str) -> dict[str, list[str] | str]:
    """Pull bullets out of the markdown body sections."""
    sections = {}
    headings = {
        "## Executive Status": "executive_status",
        "## Highlights": "highlights",
        "## Lowlights": "lowlights",
        "## Progress Summary": "progress_summary",
        "## Recommended Actions": "recommended_actions",
        "## Delta vs. previous snapshot": "delta",
    }
    # split on lines starting with "## "
    parts = re.split(r"(?m)^## ", body)
    for part in parts[1:]:
        first_nl = part.find("\n")
        if first_nl == -1:
            continue
        heading = "## " + part[:first_nl].strip()
        body_text = part[first_nl + 1:].strip()
        # match heading prefix loosely (Delta has a date appended)
        slug = next(
            (key for prefix, key in headings.items() if heading.startswith(prefix)),
            None,
        )
        if not slug:
            continue
        bullets = [l[2:].strip() for l in body_text.splitlines()
                   if l.startswith("- ") or l.startswith("* ")]
        sections[slug] = bullets if bullets else body_text
    return sections


# --- Writing -----------------------------------------------------------------

def write_snapshot(snap: Snapshot, md_path: Path) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_render(snap))


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, (int, float, bool)):
        return str(v).lower() if isinstance(v, bool) else str(v)
    s = str(v)
    if any(ch in s for ch in ":#[]{},'\"") or s.strip() != s:
        return json.dumps(s, ensure_ascii=False)
    return s


def _render(snap: Snapshot) -> str:
    fm_lines: list[str] = ["---"]
    fm_lines.append(f"initiative_key: {_yaml_scalar(snap.initiative_key)}")
    fm_lines.append(f"initiative_title: {_yaml_scalar(snap.initiative_title)}")
    fm_lines.append(f"snapshot_iso: {snap.snapshot_iso}")
    fm_lines.append(f"snapshot_date: {snap.snapshot_date}")
    if snap.html_file:
        fm_lines.append(f"html_file: {snap.html_file}")
    fm_lines.append(f"previous_snapshot: {snap.previous_snapshot or 'null'}")
    fm_lines.append(f"fetch_mode: {snap.fetch_mode}")
    fm_lines.append("rag:")
    fm_lines.append(f"  status: {snap.rag.get('status', 'yellow')}")
    fm_lines.append(f"  label: {_yaml_scalar(snap.rag.get('label', ''))}")
    fm_lines.append(f"  headline: {_yaml_scalar(snap.rag.get('headline', ''))}")
    fm_lines.append("scope:")
    for k, v in snap.scope.items():
        fm_lines.append(f"  {k}: {v}")
    fm_lines.append("counts_by_status:")
    for k, v in snap.counts_by_status.items():
        fm_lines.append(f"  {_yaml_scalar(k)}: {v}")
    fm_lines.append("tracks:")
    for name, fields in snap.tracks.items():
        inline = ", ".join(f"{k}: {_yaml_scalar(v)}" for k, v in fields.items())
        fm_lines.append(f"  {name}: {{ {inline} }}")
    fm_lines.append(f"linked_epics: [{', '.join(snap.linked_epics)}]")
    fm_lines.append("items:")
    for it in snap.items:
        fm_lines.append(f"  - key: {it.key}")
        for f in ("type", "summary", "status", "sp", "track", "assignee",
                 "updated", "pr_url", "pr_state", "pr_repo"):
            v = getattr(it, f)
            fm_lines.append(f"    {f}: {_yaml_scalar(v)}")
    fm_lines.append(f"sources_queried: [{', '.join(snap.sources_queried)}]")
    fm_lines.append("---")

    body_lines: list[str] = ["", f"# {snap.initiative_key} — Snapshot {snap.snapshot_date}"]
    sections = [
        ("Executive Status", snap.narrative.get("executive_status", [])),
        ("Highlights", snap.narrative.get("highlights", [])),
        ("Lowlights", snap.narrative.get("lowlights", [])),
        ("Progress Summary", snap.narrative.get("progress_summary", [])),
        ("Recommended Actions", snap.narrative.get("recommended_actions", [])),
    ]
    for heading, bullets in sections:
        if not bullets:
            continue
        body_lines.append("")
        body_lines.append(f"## {heading}")
        if isinstance(bullets, list):
            body_lines.extend(f"- {b}" for b in bullets)
        else:
            body_lines.append(bullets)
    if snap.narrative.get("delta"):
        body_lines.append("")
        body_lines.append(f"## Delta vs. previous snapshot ({snap.previous_snapshot or ''})")
        bullets = snap.narrative["delta"]
        if isinstance(bullets, list):
            body_lines.extend(f"- {b}" for b in bullets)
        else:
            body_lines.append(bullets)

    return "\n".join(fm_lines + body_lines) + "\n"
