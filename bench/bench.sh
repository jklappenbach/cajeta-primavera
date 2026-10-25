#!/usr/bin/env bash
# bench.sh — run the primavera benchmarks (cajeta bench/primavera/*.md) into
# results/<machine>/<run-id>/{results.csv,env.csv}, run-id
# <ISO-8601-basic-UTC>-<cajeta-version> (benchmark-reference spec §4.1).
#
#   ./bench.sh --list                          the page ids
#   ./bench.sh --bench cold-start              primavera only
#   ./bench.sh --bench cold-start --competitors   primavera and every pinned competitor
#   ./bench.sh --competitors                   every id, every platform (the full run)
#   ./bench.sh --smoke ...                     CAJETA_BENCH_SMOKE=1: rows tagged smoke, written
#                                              under build/results/, never results/
#   ./bench.sh --machine phoenix ...           the machine column (default: the hostname)
#   ./bench.sh --no-build ...                  reuse what scripts/build-all.sh built
#   ./bench.sh --force ...                     run although the box is not quiet
#
# A published (non-smoke) run refuses to start unless the load average is
# under 1 (spec §9.1); the evidence goes into env.csv. LATEST names the run.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

ARGS=(); COMPETITORS=0; BUILD=1; FORCE=0; LIST=0
MACHINE="${CAJETA_BENCH_MACHINE:-}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --list) LIST=1; shift ;;
        --competitors) COMPETITORS=1; shift ;;
        --smoke) export CAJETA_BENCH_SMOKE=1; shift ;;
        --no-build) BUILD=0; shift ;;
        --force) FORCE=1; shift ;;
        --machine) MACHINE="${2:?--machine needs a name}"; shift 2 ;;
        --bench|--area) ARGS+=("$1" "${2:?$1 needs a value}"); shift 2 ;;
        *) echo "bench.sh: unknown argument $1" >&2; exit 2 ;;
    esac
done
[[ -n "$MACHINE" ]] || MACHINE="$(hostname -s 2>/dev/null | tr '[:upper:]' '[:lower:]')"
export CAJETA_BENCH_MACHINE="$MACHINE"

if [[ "$BUILD" == "1" ]]; then
    bash scripts/build-all.sh || exit 1
fi
BIN=build/primavera-bench
[[ -x "$BIN" ]] || { echo "bench.sh: $BIN missing; run scripts/build-all.sh" >&2; exit 1; }
if [[ "$LIST" == "1" ]]; then exec "$BIN" --list; fi

[[ "$COMPETITORS" == "1" ]] || export CAJETA_BENCH_PLATFORMS=primavera

CAJETA_VER="$(awk -F'\t' '$1 == "cajeta" {print $2}' build/toolchains.tsv)"
RUN_ID="$(date -u +%Y%m%dT%H%MZ)-${CAJETA_VER}"
SMOKE="${CAJETA_BENCH_SMOKE:-0}"
LOAD="$(cut -d' ' -f1 /proc/loadavg)"
if [[ "$SMOKE" == "1" ]]; then
    OUT="build/results/$MACHINE/$RUN_ID"
else
    OUT="results/$MACHINE/$RUN_ID"
    if awk -v l="$LOAD" 'BEGIN {exit !(l >= 1.0)}' && [[ "$FORCE" != "1" ]]; then
        echo "bench.sh: load average $LOAD is not under 1; a published run waits for a quiet box (--force to run anyway)" >&2
        exit 1
    fi
fi
mkdir -p "$OUT" build/logs
: > build/pids.txt

export CAJETA_BENCH_RUN_ID="$RUN_ID"
export CAJETA_BENCH_RUN_TS="$(date +%s)"
export CAJETA_BENCH_CAJETA_VERSION="$CAJETA_VER"
export CAJETA_BENCH_FLAGS="${CAJETA_BENCH_FLAGS:-$(cat apps/web/FLAGS 2>/dev/null || echo '--release -O3 -march=native')}"

echo "[bench] start $(date -u +%H:%M:%SZ), machine $MACHINE, run $RUN_ID, load $LOAD${SMOKE:+ (smoke=$SMOKE)}"
"$BIN" --run --out "$OUT/results.csv" ${ARGS[@]+"${ARGS[@]}"}
RC=$?

# Anything this run started and left behind: by recorded PID only.
while read -r pid what; do
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && { echo "[bench] killing leftover $what ($pid)"; kill -9 "$pid"; }
done < build/pids.txt

{
    echo "load_average_start,$LOAD"
    echo "platforms,${CAJETA_BENCH_PLATFORMS:-all}"
} >> "$OUT/env.csv"
if [[ "$SMOKE" != "1" && $RC -eq 0 ]]; then
    echo "$RUN_ID" > "results/$MACHINE/LATEST"
fi
echo "[bench] end $(date -u +%H:%M:%SZ): $OUT (exit $RC)"
exit $RC
