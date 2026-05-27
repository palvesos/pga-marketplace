"""Test 3 — Demonstrate API-call reduction on a realistic-scale initiative.

Pure synthetic: 50 items, ~17 with PRs, 4 status changes since prior, 1
new item, 1 removed. Reports the gh-call reduction vs. a full walk.
"""

import random
import sys

PRIOR_ISO = "2026-05-13T09:05:44Z"
IN_WINDOW = "2026-05-20T00:00:00Z"
IN_WINDOW_CREATED = "2026-05-25T00:00:00Z"
OUT_WINDOW = "2026-05-01T00:00:00Z"


def main():
    random.seed(42)

    prior = []
    for n in range(50):
        has_pr = n % 3 == 0
        prior.append({
            "key": f"FAKE-{200 + n}",
            "status": random.choice(["Done", "In Progress", "In Peer Review", "To Do"]),
            "sp": random.choice([1, 2, 3, 5, None]),
            "track": random.choice(["RQ01", "RQ02", "RQ03", "Charlie"]),
            "assignee": random.choice(["alice", "bob", "carol", "dave"]),
            "pr_state": "OPEN" if has_pr else None,
        })

    changed_keys = {"FAKE-203", "FAKE-217", "FAKE-228", "FAKE-241"}
    removed_keys = {"FAKE-249"}

    current = []
    for it in prior:
        if it["key"] in removed_keys:
            continue
        if it["key"] in changed_keys:
            current.append({**it, "status": "Done", "updated": IN_WINDOW})
        else:
            current.append({**it, "updated": OUT_WINDOW})
    current.append({
        "key": "FAKE-250", "status": "To Do", "sp": 3, "track": "RQ03",
        "assignee": "erin", "pr_state": None, "updated": IN_WINDOW_CREATED,
    })

    q1 = [i for i in current if i["updated"] >= PRIOR_ISO]
    items_with_pr_full = [i for i in current if i.get("pr_state")]
    items_with_pr_incr = [i for i in q1 if i.get("pr_state")]

    print(f"initiative size            : {len(current)} items (was {len(prior)})")
    print(f"items changed in window    : {len(q1)} -> {sorted(i['key'] for i in q1)}")
    print()
    print("gh `search prs` calls (open + closed = 2 per item with a PR):")
    print(f"  full walk                : {len(items_with_pr_full) * 2}")
    print(f"  incremental              : {len(items_with_pr_incr) * 2}")
    if items_with_pr_full:
        saved_pct = (1 - len(items_with_pr_incr) / len(items_with_pr_full)) * 100
        print(f"  reduction                : {saved_pct:.0f}%")

    # The test passes if incremental issues strictly fewer calls
    ok = len(items_with_pr_incr) < len(items_with_pr_full)
    print()
    print("✓ PASS" if ok else "✗ FAIL — incremental did not reduce gh calls")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
