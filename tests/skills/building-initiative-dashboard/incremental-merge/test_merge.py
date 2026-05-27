"""Test 1 — Incremental merge produces the same item set as a full walk.

Setup:
  prior  : fixtures/prior_snapshot.md (10 items, 2026-05-13)
  current: fixtures/current_state.json (11 items, 2026-05-27)

Expected:
  merge(prior, q1=changed, q2=added, q3=keys) == full-walk projection of current
"""

import sys
from _lib import (
    parse_prior_md,
    load_current_state,
    query_changed,
    query_added,
    query_reconcile_keys,
    merge,
    normalize,
)


def main():
    prior_iso, prior_items = parse_prior_md()
    current = load_current_state()
    current_items = current["items"]

    q1 = query_changed(current_items, prior_iso)
    q2 = query_added(current_items, {i["key"] for i in prior_items})
    q3 = query_reconcile_keys(current_items)

    merged = merge(prior_items, q1, q2, q3)
    full_walk = [normalize(i) for i in current_items]

    by_merged = {i["key"]: i for i in merged}
    by_full = {i["key"]: i for i in full_walk}

    only_merged = sorted(set(by_merged) - set(by_full))
    only_full = sorted(set(by_full) - set(by_merged))
    diffs = [(k, by_merged[k], by_full[k])
             for k in sorted(set(by_merged) & set(by_full))
             if by_merged[k] != by_full[k]]

    print(f"prior items                : {len(prior_items)}")
    print(f"current full-walk items    : {len(current_items)}")
    print(f"query 1 (changed)          : {len(q1)} -> {sorted(i['key'] for i in q1)}")
    print(f"query 2 (added)            : {len(q2)} -> {sorted(i['key'] for i in q2)}")
    print(f"query 3 (keys reconcile)   : {len(q3)}")
    print(f"merged items               : {len(merged)}")
    print()
    print(f"keys in merge only         : {only_merged or '∅'}")
    print(f"keys in full only          : {only_full or '∅'}")
    print(f"field-level diffs          : {len(diffs)}")
    for k, m, f in diffs:
        print(f"  {k}:\n    merge={m}\n    full ={f}")

    ok = not only_merged and not only_full and not diffs
    print()
    print("✓ PASS" if ok else "✗ FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
