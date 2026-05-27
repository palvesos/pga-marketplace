"""Shared helpers for the incremental-merge tests.

These scripts simulate Step 1.5 of the building-initiative-dashboard
SKILL.md against fixtures committed under ./fixtures/ — no real Jira or
GitHub calls. They validate that the merge algorithm produces a final
item set identical to a full walk of Jira.
"""

import json
import re
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
PRIOR_MD = FIXTURES / "prior_snapshot.md"
CURRENT_JSON = FIXTURES / "current_state.json"

PR_FIELDS = ("pr_url", "pr_state", "pr_repo")
TRACKED_FIELDS = ("key", "type", "summary", "status", "sp", "track", "assignee") + PR_FIELDS


def _coerce(v):
    s = v.strip().strip('"')
    if s == "null" or s == "None":
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def parse_prior_md(path=PRIOR_MD):
    """Extract `snapshot_iso` and the `items` list from a state .md.

    Handles the multi-line YAML block-style format documented in Step 7
    of the SKILL.md."""
    text = Path(path).read_text()
    fm = text.split("---", 2)[1]
    snapshot_iso = re.search(r"^snapshot_iso:\s*(\S+)", fm, re.MULTILINE).group(1)
    # Grab the items: block — everything from "items:" until the next
    # top-level key (a line starting with a letter at column 0 inside the FM).
    m = re.search(r"^items:\n((?:  .*\n)+)", fm, re.MULTILINE)
    items_block = m.group(1)
    items = []
    current = None
    for line in items_block.splitlines():
        if re.match(r"^  - key:\s*", line):
            if current is not None:
                items.append(current)
            current = {"key": _coerce(line.split(":", 1)[1])}
        else:
            m2 = re.match(r"^    (\w+):\s*(.*)$", line)
            if m2 and current is not None:
                current[m2.group(1)] = _coerce(m2.group(2))
    if current is not None:
        items.append(current)
    return snapshot_iso, items


def load_current_state(path=CURRENT_JSON):
    return json.loads(Path(path).read_text())


def normalize(item):
    """Project either a prior-md row or a current-state row onto the tracked fields."""
    return {f: item.get(f) for f in TRACKED_FIELDS}


# --- Step 1.5 simulation -----------------------------------------------------

def query_changed(current_items, prior_iso):
    """JQL equivalent: updated >= <prior_iso>."""
    return [i for i in current_items if i["updated"] >= prior_iso]


def query_added(current_items, prior_keys):
    """JQL equivalent: created >= <prior_iso>.
    Approximated here by 'key not in prior set' — both filters yield the
    same set for new tickets in the relevant window."""
    return [i for i in current_items if i["key"] not in prior_keys]


def query_reconcile_keys(current_items):
    """JQL equivalent: full scope JQL, --fields key only."""
    return [i["key"] for i in current_items]


def merge(prior_items, q1_changed, q2_added, q3_keys):
    """Step 1.5 merge: prior + q1 overwrites + q2 inserts, drop anything not in q3."""
    working = {i["key"]: normalize(i) for i in prior_items}
    for it in q1_changed:
        working[it["key"]] = normalize(it)
    for it in q2_added:
        working.setdefault(it["key"], normalize(it))
    return [working[k] for k in q3_keys if k in working]
