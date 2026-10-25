#!/usr/bin/env bash
# build-all.sh — build everything the primavera benchmarks run, from bench/.
#
#   1. resolve the toolchains (cajeta, java, dotnet, the FastAPI venv, oha) and
#      record their versions in build/toolchains.tsv;
#   2. write build/apps.tsv: apps/apps.tsv and competitors/*/apps.tsv with
#      {cajeta}, {dotnet} and {python} resolved;
#   3. check the generated DI sources are current (di/generate.py --check);
#   4. build the harness (build/primavera-bench) unless --no-harness;
#   5. build every app, each capped at BUILD_CAP seconds (default 900), and
#      write build/status/<key>-<app>: `ok`, or `skipped: <reason>` when it
#      cannot build here. A Maven build runs offline first and, when the
#      dependencies are not cached yet, once online to fetch them.
#
# primavera's own apps must build: their failure fails this script. A
# competitor that cannot build is recorded and the run carries on; its rows
# are `skipped` with the reason.
#
# Env: CAJETA, DOTNET, BENCH_PYTHON, OHA override the resolved tools;
#      BUILD_CAP (seconds per app build).
set -uo pipefail

BENCH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BENCH"
HARNESS=1
[[ "${1:-}" == "--no-harness" ]] && HARNESS=0
CAP="${BUILD_CAP:-900}"
mkdir -p build/status build/logs

# ---- 1. toolchains -----------------------------------------------------------
if [[ -z "${CAJETA:-}" ]]; then
    if command -v cajeta >/dev/null 2>&1; then CAJETA="$(command -v cajeta)"
    else CAJETA="$(cd "$BENCH/../.." && pwd)/cajeta/build/src/cajeta"; fi
fi
[[ -x "$CAJETA" ]] || { echo "build-all: no cajeta compiler at $CAJETA (set CAJETA=)" >&2; exit 1; }
if [[ -z "${DOTNET:-}" ]]; then
    if [[ -x "$HOME/.dotnet/dotnet" ]]; then DOTNET="$HOME/.dotnet/dotnet"
    else DOTNET="$(command -v dotnet || echo dotnet)"; fi
fi
if [[ -z "${BENCH_PYTHON:-}" ]]; then
    BENCH_PYTHON="$(cd "$BENCH/../.." && pwd)/cajeta/bench/competitors/python/.venv/bin/python"
fi
if [[ -z "${OHA:-}" ]]; then
    if [[ -x "$HOME/.cargo/bin/oha" ]]; then OHA="$HOME/.cargo/bin/oha"; else OHA="$(command -v oha || echo oha)"; fi
fi

cajeta_v="$("$CAJETA" --version 2>/dev/null | awk 'NR==1 {print $2}')"
java_v="$(java -version 2>&1 | awk -F'"' 'NR==1 {print $2}') ($(java -version 2>&1 | sed -n 2p | sed -e 's/ (build.*//' -e 's/^OpenJDK Runtime Environment //'))"
dotnet_v="$("$DOTNET" --list-runtimes 2>/dev/null | awk '/Microsoft.NETCore.App/ {v=$2} END {print v}')"
python_v="$("$BENCH_PYTHON" --version 2>/dev/null | awk '{print $2}')"
oha_v="$("$OHA" --version 2>/dev/null | awk '{print $2}')"
native_v="$(command -v native-image >/dev/null 2>&1 && native-image --version 2>&1 | head -1 || echo absent)"
{
    printf 'cajeta\t%s\n' "$cajeta_v"
    printf 'java\t%s\n' "$java_v"
    printf 'dotnet\t%s\n' "$dotnet_v"
    printf 'python\t%s\n' "$python_v"
    printf 'oha\t%s\n' "$oha_v"
    printf 'native-image\t%s\n' "$native_v"
} > build/toolchains.tsv
echo "[build-all] cajeta $cajeta_v; java $java_v; dotnet $dotnet_v; python $python_v; oha $oha_v; native-image $native_v"

# ---- 2. the app table ----------------------------------------------------------
cat apps/apps.tsv competitors/*/apps.tsv | grep -v '^#' | grep -v '^[[:space:]]*$' \
    | sed -e "s#{cajeta}#$CAJETA#g" -e "s#{dotnet}#$DOTNET#g" -e "s#{python}#$BENCH_PYTHON#g" \
    > build/apps.tsv
echo "[build-all] $(wc -l < build/apps.tsv) apps in build/apps.tsv"

# ---- 3. the DI graph is the generator's ------------------------------------------
python3 di/generate.py --check >/dev/null || { echo "build-all: di sources are stale; run python3 di/generate.py" >&2; exit 1; }

# ---- 4. the harness --------------------------------------------------------------
if [[ "$HARNESS" == "1" ]]; then
    t=$(date +%s)
    "$CAJETA" build > build/logs/build-harness.log 2>&1 \
        || { echo "build-all: the harness did not build (build/logs/build-harness.log)" >&2; tail -5 build/logs/build-harness.log >&2; exit 1; }
    echo "[build-all] harness built in $(( $(date +%s) - t ))s"
fi

# ---- 5. the apps -------------------------------------------------------------------
status() { printf '%s\n' "$2" > "build/status/$1"; echo "[build-all] $1: $2"; }

hard_fail=0
while IFS=$'\t' read -r key app lang platform version dir clean build run; do
    id="$key-$app"
    log="build/logs/build-$id.log"
    if [[ "$key" == *-native ]] && ! command -v native-image >/dev/null 2>&1; then
        status "$id" "skipped: GraalVM native-image is not installed"; continue
    fi
    if [[ "$build" == "-" ]]; then
        if [[ "$lang" == "python" ]]; then
            if "$BENCH_PYTHON" -c 'import fastapi, uvicorn, jinja2' > "$log" 2>&1; then status "$id" ok
            else status "$id" "skipped: the FastAPI venv at $BENCH_PYTHON lacks fastapi, uvicorn or jinja2"; fi
        else
            status "$id" ok
        fi
        continue
    fi
    t=$(date +%s)
    (cd "$dir" && timeout "$CAP" sh -c "$build") > "$log" 2>&1
    rc=$?
    if [[ $rc -ne 0 && "$build" == *" -o "* ]]; then
        # Dependencies not cached yet: fetch them once, online.
        online="${build/ -o / }"
        echo "[build-all] $id: offline build failed, fetching dependencies online" >> "$log"
        (cd "$dir" && timeout "$CAP" sh -c "$online") >> "$log" 2>&1
        rc=$?
    fi
    secs=$(( $(date +%s) - t ))
    if [[ $rc -eq 0 ]]; then
        status "$id" ok
        echo "[build-all]   ($secs s)"
    elif [[ $rc -eq 124 ]]; then
        status "$id" "skipped: the build passed the ${CAP} s cap on this machine"
    else
        why="$(grep -v '^\s*$' "$log" | tail -1 | tr '\t' ' ' | cut -c1-200)"
        status "$id" "skipped: the build failed on this machine (exit $rc: $why)"
    fi
    if [[ "$key" == "primavera" && $rc -ne 0 ]]; then hard_fail=1; fi
done < build/apps.tsv

if [[ $hard_fail -ne 0 ]]; then
    echo "build-all: primavera's own apps did not build (build/logs/build-primavera-*.log)" >&2
    exit 1
fi
echo "[build-all] done"
