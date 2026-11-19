#!/usr/bin/env python3
"""
hd_run_tools.py (v1.1) - read-only helpers for independent review.

  python hd_run_tools.py compare <run_dir_A> <run_dir_B>      uninterrupted vs resumed comparison
  python hd_run_tools.py hash    <dir> <out.json>            record SHA-256 of every file under dir
  python hd_run_tools.py verify  <dir> <hashes.json>         prove a dir is byte-for-byte unchanged

Nothing here modifies the directories it reads (hash/verify write only the JSON path you name).
"""
import hashlib
import json
import os
import sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hashes(root):
    out = {}
    for dp, _, fns in os.walk(root):
        for fn in sorted(fns):
            p = os.path.join(dp, fn)
            out[os.path.relpath(p, root).replace("\\", "/")] = sha256(p)
    return out


def load(path):
    with open(path, "rb") as f:
        return f.read()


def compare(a, b):
    """Compare content that must be identical between an uninterrupted run and a resumed run."""
    results = []

    def chk(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    for fn in ("data_quality.csv", "acquisition_failures.csv"):
        pa, pb = os.path.join(a, fn), os.path.join(b, fn)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            chk(fn + " byte-identical", False, "missing in one run")
        else:
            chk(fn + " byte-identical", load(pa) == load(pb), "sha256 A=%s B=%s" % (sha256(pa)[:12], sha256(pb)[:12]))
    ma = json.loads(load(os.path.join(a, "manifest.json")).decode("utf-8"))
    mb = json.loads(load(os.path.join(b, "manifest.json")).decode("utf-8"))
    for tf in ("M1", "M15"):
        da, db = ma.get("data_quality", {}).get(tf, {}), mb.get("data_quality", {}).get(tf, {})
        for key in ("bars_audited", "first_bar_audited", "last_bar_audited", "bar_digest_crc32",
                    "gap_events", "missing_bars_total", "duplicate_timestamps", "out_of_order",
                    "ohlc_invalid_bars", "coverage_status"):
            chk("%s.%s equal" % (tf, key), da.get(key) == db.get(key), "A=%r B=%r" % (da.get(key), db.get(key)))
        chk("%s full audit block equal" % tf, da == db)
    for key in ("event_rows_written", "event_rows_suppressed_by_cap", "acq_rows_written", "suitability",
                "acquisition_complete", "status"):
        chk("manifest.%s equal" % key, ma.get(key) == mb.get(key), "A=%r B=%r" % (ma.get(key), mb.get(key)))
    sa, sb = os.path.join(a, "data_quality_summary.csv"), os.path.join(b, "data_quality_summary.csv")
    if os.path.exists(sa) and os.path.exists(sb):
        chk("data_quality_summary.csv byte-identical", load(sa) == load(sb))
    pb = mb.get("parent_run_id") or ""
    chk("lineage: B is a fresh run or names A as parent", pb in ("", os.path.basename(a.rstrip("/\\"))),
        "B.parent_run_id=%r" % pb)
    return results


def main(argv):
    if len(argv) >= 4 and argv[1] == "compare":
        res = compare(argv[2], argv[3])
        bad = 0
        for name, ok, detail in res:
            print("%-6s %s %s" % ("PASS" if ok else "FAIL", name, ("(" + detail + ")") if detail and not ok else ""))
            bad += 0 if ok else 1
        print("RESULT:", "ALL PASS" if bad == 0 else "%d FAILED" % bad)
        return 0 if bad == 0 else 1
    if len(argv) == 4 and argv[1] == "hash":
        with open(argv[3], "w") as f:
            json.dump(tree_hashes(argv[2]), f, indent=1, sort_keys=True)
        print("hashed", argv[2], "->", argv[3])
        return 0
    if len(argv) == 4 and argv[1] == "verify":
        with open(argv[3]) as f:
            before = json.load(f)
        after = tree_hashes(argv[2])
        added = sorted(set(after) - set(before))
        removed = sorted(set(before) - set(after))
        changed = sorted(k for k in before if k in after and before[k] != after[k])
        print("added:", added, "removed:", removed, "changed:", changed)
        ok = not (added or removed or changed)
        print("RESULT:", "UNCHANGED" if ok else "MODIFIED")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
