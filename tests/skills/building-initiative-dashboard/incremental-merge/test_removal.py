"""Test 2 — Items removed from scope between snapshots are dropped.

Mutates fixtures/current_state.json in-memory by removing FAKE-108, then
runs the merge. The reconcile query (q3) must cause FAKE-108 to be
dropped from the working set inherited from the prior snapshot.
"""

import sys
from _lib import (
    parse_prior_md,
    load_current_state,
    query_changed,
    query_added,
    query_reconcile_keys,
    merge,
)


def main():
    prior_iso, prior_items = parse_prior_md()
    current = load_current_state()
    current_items = [i for i in current["items"] if i["key"] != "FAKE-108"]

    q1 = query_changed(current_items, prior_iso)
    q2 = query_added(current_items, {i["key"] for i in prior_items})
    q3 = query_reconcile_keys(current_items)

    merged = merge(prior_items, q1, q2, q3)
    merged_keys = sorted(i["key"] for i in merged)

    print(f"removed from current state : FAKE-108")
    print(f"prior items                : {len(prior_items)} (includes FAKE-108)")
    print(f"current items              : {len(current_items)}")
    print(f"merged keys                : {merged_keys}")
    print()

    ok = "FAKE-108" not in merged_keys and len(merged) == len(current_items)
    print("✓ PASS" if ok else "✗ FAIL — removal not handled correctly")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
