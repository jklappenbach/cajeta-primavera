#!/usr/bin/env python3
"""amend.py <results.csv> <ledger.tsv>

Writes the ledger onto the rows dev.cajeta.bench wrote (bench.primavera.Ledger
explains why there is one): each ledger line `benchmark  variant  column
value` sets that column on the row whose benchmark and variant match, where
the variant is the harness's (`spring-boot@64`); `notes+` appends to notes,
and a `variant` line, applied last, renames the variant to the page's label.

A row the ledger knows nothing about is left as the harness wrote it. A
skipped or failed row takes the identity columns and notes only, never a
measured figure. env.csv beside results.csv gains every toolchain version in
build/toolchains.tsv, as `toolchain_<name>`.
"""
import csv
import os
import sys

MEASURED = {"min_ns", "median_ns", "mean_ns", "p95_ns", "throughput", "peak_rss_kb",
            "trials", "warmup"}


def main():
    results, ledger = sys.argv[1], sys.argv[2]
    edits = {}
    if os.path.exists(ledger):
        for line in open(ledger, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            bench, variant, col, value = parts
            edits.setdefault((bench, variant), []).append((col, value))
    with open(results, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return 0
    header = rows[0]
    idx = {h: i for i, h in enumerate(header)}
    for r in rows[1:]:
        key = (r[idx["benchmark"]], r[idx["variant"]])
        ok = r[idx["status"]] == "ok"
        rename = None
        notes = []
        for col, value in edits.get(key, []):
            if col == "variant":
                rename = value
            elif col == "notes+":
                notes.append(value)
            elif col in idx:
                if col in MEASURED and not ok:
                    continue
                r[idx[col]] = value
        if notes:
            have = r[idx["notes"]]
            parts = [p.strip() for p in have.split(";") if p.strip()]
            smoke = "smoke" in parts
            parts = [p for p in parts if p != "smoke"] + notes + (["smoke"] if smoke else [])
            r[idx["notes"]] = "; ".join(parts)
        if rename is not None:
            r[idx["variant"]] = rename
    with open(results, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)

    env = os.path.join(os.path.dirname(results) or ".", "env.csv")
    tools = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "toolchains.tsv")
    if os.path.exists(env) and os.path.exists(tools):
        have = {line.split(",", 1)[0] for line in open(env, encoding="utf-8")}
        with open(env, "a", encoding="utf-8") as f:
            for line in open(tools, encoding="utf-8"):
                name, _, value = line.rstrip("\n").partition("\t")
                k = f"toolchain_{name}"
                if name and k not in have:
                    v = value.replace('"', "'")
                    f.write(f'{k},"{v}"\n' if "," in v else f"{k},{v}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
