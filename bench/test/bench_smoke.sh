#!/usr/bin/env bash
# bench_smoke.sh — the primavera benchmark project's smoke test
# (cajeta agents/benchmark-reference-plan.md 19.1.1 and 19.1.2).
#
# Builds the bench harness, the primavera bench server and DI app, and every
# competitor app (each capped; a competitor that cannot build here records a
# reason and must then appear as a `skipped` row carrying it), then runs every
# page id in smoke mode (CAJETA_BENCH_SMOKE=1: warmup 1, trials 3, a few
# seconds of load, 3 launches instead of 20) and checks the rows:
#
#   * --list names exactly the seven page ids, each under area `primavera`;
#   * results.csv is schema v2 (37 columns) and every row is tagged smoke;
#   * every page id has a row per competitor the page names, plus primavera's;
#     a row is `ok`, or `skipped` with a reason (native-image rows are skipped
#     because GraalVM native-image is not installed; FastAPI has no build);
#   * primavera's row is `ok` on every id;
#   * a competitor that built is `ok` (its byte comparison passed before load);
#   * throughput rows carry req/s, latency, errors=0; memory rows peak_rss_kb;
#   * every row's platform names the framework and a version;
#   * no process the run started is still alive afterwards (pids file).
#
# Usage: bench/test/bench_smoke.sh [page-id-name ...]   (default: all seven)
# Env:   CAJETA=<compiler>   (default: cajeta on PATH, else the sibling build)
#        SMOKE_OUT=<dir>     (default: bench/build/smoke)
#        SKIP_BUILD=1        reuse the built harness, server and competitors
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"
if [[ -z "${CAJETA:-}" ]]; then
    if command -v cajeta >/dev/null 2>&1; then CAJETA="$(command -v cajeta)"
    else CAJETA="$BENCH/../../cajeta/build/src/cajeta"; fi
fi
export CAJETA
OUT="${SMOKE_OUT:-$BENCH/build/smoke}"
mkdir -p "$OUT"

ALL_IDS=(register-user-json templated-page cold-start idle-rss loaded-rss build-time di-graph-100-startup)
if [[ $# -gt 0 ]]; then IDS=("$@"); else IDS=("${ALL_IDS[@]}"); fi

fails=0
fail() { echo "FAIL: $*"; fails=$((fails + 1)); }
pass() { echo "ok:   $*"; }
now() { date +%s; }

T0="$(now)"
echo "[smoke] start $(date -u +%H:%M:%SZ); compiler $CAJETA"

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
    t="$(now)"
    if ! (cd "$BENCH" && bash scripts/build-all.sh) >"$OUT/build.log" 2>&1; then
        fail "build-all.sh failed (see $OUT/build.log)"
        tail -30 "$OUT/build.log"
        echo "[smoke] $fails failure(s)"
        exit 1
    fi
    echo "[smoke] build-all: $(( $(now) - t ))s"
fi

BIN="$BENCH/build/primavera-bench"
[[ -x "$BIN" ]] || { fail "harness binary $BIN missing"; echo "[smoke] $fails failure(s)"; exit 1; }

# ---- --list -------------------------------------------------------------
LIST="$("$BIN" --list 2>&1)"
for id in "${ALL_IDS[@]}"; do
    if grep -qE "^ *primavera/$id +\[cpu\]" <<<"$LIST"; then pass "--list names primavera/$id"
    else fail "--list does not name primavera/$id"; fi
done
n_listed="$(grep -cE '^ *primavera/' <<<"$LIST")"
[[ "$n_listed" == "${#ALL_IDS[@]}" ]] && pass "--list names ${#ALL_IDS[@]} benchmarks" \
    || fail "--list names $n_listed benchmarks, expected ${#ALL_IDS[@]}"

# ---- runs ---------------------------------------------------------------
PIDS="$BENCH/build/pids.txt"
for id in "${IDS[@]}"; do
    dir="$OUT/$id"
    rm -rf "$dir"; mkdir -p "$dir"
    : >"$PIDS"
    t="$(now)"
    (cd "$BENCH" && CAJETA_BENCH_SMOKE=1 "$BIN" --run --bench "$id" --out "$dir/results.csv") \
        >"$dir/run.log" 2>&1
    rc=$?
    echo "[smoke] $id: exit $rc in $(( $(now) - t ))s"
    [[ $rc -eq 0 ]] || { fail "$id exited $rc"; tail -20 "$dir/run.log"; }

    # Every PID the run recorded is gone.
    while read -r pid what; do
        [[ -n "$pid" ]] || continue
        if kill -0 "$pid" 2>/dev/null; then
            fail "$id left pid $pid ($what) running"; kill -9 "$pid" 2>/dev/null
        fi
    done <"$PIDS"

    python3 "$HERE/check_rows.py" "$id" "$dir/results.csv" "$BENCH/build/status" \
        || fails=$((fails + 1))
done

echo "[smoke] total $(( $(now) - T0 ))s"
if [[ $fails -gt 0 ]]; then echo "[smoke] $fails failure(s)"; exit 1; fi
echo "[smoke] all green"
