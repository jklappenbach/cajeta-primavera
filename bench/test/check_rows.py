#!/usr/bin/env python3
"""check_rows.py <page-id-name> <results.csv> <status-dir>

The row assertions of bench_smoke.sh for one page id. The `library` column
carries the stable platform key (primavera, spring-boot, quarkus-jvm, ...);
`platform` carries the framework name with its version, as the pages say.

<status-dir>/<key> is what scripts/build-all.sh wrote for each app: `ok`, or
`skipped: <reason>` when it could not build here. A competitor that built must
be `ok`; one that did not must be `skipped` with that reason.
"""
import csv
import re
import sys

V2 = ("schema_version,run_id,timestamp_unix,benchmark,area,dataset_name,dataset_bytes,"
      "dataset_sha256,input_size,language,language_version,library,library_version,flags,"
      "warmup,trials,min_ns,median_ns,mean_ns,p95_ns,throughput,throughput_unit,peak_rss_kb,"
      "cgroup_peak_kb,alloc_bytes,alloc_count,working_set_kb,status,check_ok,notes,variant,"
      "backend,machine,os,driver,model,platform").split(",")

SERVICE = ["primavera", "spring-boot", "quarkus-jvm", "quarkus-native",
           "micronaut-jvm", "micronaut-native", "aspnetcore", "fastapi"]
EXPECTED = {
    "register-user-json": (SERVICE, ["64 connections", "512 connections"], "throughput"),
    "templated-page": (["primavera", "spring-boot", "quarkus-jvm", "aspnetcore", "fastapi"],
                       ["64 connections"], "throughput"),
    "cold-start": (SERVICE, [""], "time"),
    "idle-rss": (SERVICE, [""], "memory"),
    "loaded-rss": (SERVICE, [""], "memory"),
    "build-time": (SERVICE, [""], "time"),
    "di-graph-100-startup": (["primavera", "spring-boot", "quarkus-jvm", "micronaut-jvm",
                              "aspnetcore", "fastapi"], [""], "time"),
}
LANG = {"primavera": "cajeta", "spring-boot": "java", "quarkus-jvm": "java",
        "quarkus-native": "java", "micronaut-jvm": "java", "micronaut-native": "java",
        "aspnetcore": "csharp", "fastapi": "python"}
PLATFORM_NAME = {"primavera": "primavera", "spring-boot": "Spring Boot",
                 "quarkus-jvm": "Quarkus", "quarkus-native": "Quarkus",
                 "micronaut-jvm": "Micronaut", "micronaut-native": "Micronaut",
                 "aspnetcore": "ASP.NET Core", "fastapi": "FastAPI"}

fails = 0


def fail(msg):
    global fails
    fails += 1
    print(f"FAIL: {msg}")


def ok(msg):
    print(f"ok:   {msg}")


def status_of(status_dir, key, page):
    """('ok', '') or ('skipped', reason) for the app the row measures."""
    if key == "primavera":
        return ("ok", "")
    if key.endswith("-native"):
        return ("skipped", "GraalVM native-image is not installed")
    if page == "build-time" and key == "fastapi":
        return ("skipped", "no build step")
    app = "di" if page == "di-graph-100-startup" else "web"
    try:
        text = open(f"{status_dir}/{key}-{app}").read().strip()
    except OSError:
        return ("missing", f"no build status for {key}-{app}")
    if text == "ok":
        return ("ok", "")
    return ("skipped", text.split(":", 1)[1].strip() if ":" in text else text)


def main():
    page, path, status_dir = sys.argv[1:4]
    keys, variants, metric = EXPECTED[page]
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows or rows[0] != V2:
        fail(f"{page}: header is not schema v2 ({len(rows[0]) if rows else 0} columns)")
        return 1
    recs = [dict(zip(V2, r)) for r in rows[1:]]
    for r in recs:
        if len(r) != 37:
            fail(f"{page}: a row has {len(r)} columns")
        if r["area"] != "primavera" or r["benchmark"] != page:
            fail(f"{page}: stray row {r['area']}/{r['benchmark']}")
        if "smoke" not in [p.strip() for p in r["notes"].split(";")]:
            fail(f"{page}: row {r['library']} '{r['variant']}' is not tagged smoke")
        if r["schema_version"] != "2" or not r["machine"] or not r["platform"]:
            fail(f"{page}: row {r['library']} lacks schema_version 2, machine or platform")

    for key in keys:
        want, reason = status_of(status_dir, key, page)
        for v in variants:
            got = [r for r in recs if r["library"] == key and r["variant"] == v]
            label = f"{page} {key} '{v}'"
            if len(got) != 1:
                fail(f"{label}: {len(got)} rows, expected 1")
                continue
            r = got[0]
            if r["language"] != LANG[key]:
                fail(f"{label}: language {r['language']}, expected {LANG[key]}")
            name = PLATFORM_NAME[key]
            if not r["platform"].startswith(name + " ") or not re.search(r"\d+\.\d+", r["platform"]):
                fail(f"{label}: platform '{r['platform']}' is not '{name} <version>'")
            if want == "missing":
                fail(f"{label}: {reason}")
                continue
            if want == "skipped":
                if r["status"] != "skipped" or reason not in r["notes"]:
                    fail(f"{label}: expected skipped ({reason}), got {r['status']}: {r['notes']}")
                else:
                    ok(f"{label}: skipped ({reason})")
                continue
            if r["status"] != "ok" or r["check_ok"] != "true":
                fail(f"{label}: status {r['status']} check {r['check_ok']}: {r['notes']}")
                continue
            if r["trials"] in ("", "0"):
                fail(f"{label}: no trials recorded")
            if metric == "throughput":
                try:
                    tp = float(r["throughput"])
                except ValueError:
                    tp = 0.0
                if tp <= 0 or r["throughput_unit"] != "req/s":
                    fail(f"{label}: throughput '{r['throughput']}' '{r['throughput_unit']}'")
                elif "errors=0" not in r["notes"] or "body=equal" not in r["notes"]:
                    fail(f"{label}: notes lack errors=0 / body=equal: {r['notes']}")
                elif int(r["median_ns"]) <= 0:
                    fail(f"{label}: no latency")
                else:
                    ok(f"{label}: {tp:.0f} req/s, p50 {int(r['median_ns']) / 1e6:.2f} ms")
            elif metric == "memory":
                if int(r["peak_rss_kb"]) <= 0:
                    fail(f"{label}: peak_rss_kb {r['peak_rss_kb']}")
                else:
                    ok(f"{label}: {int(r['peak_rss_kb']) / 1024:.1f} MiB")
            else:
                if int(r["median_ns"]) <= 0:
                    fail(f"{label}: median_ns {r['median_ns']}")
                else:
                    ok(f"{label}: median {int(r['median_ns']) / 1e6:.1f} ms over {r['trials']}")
    extra = [r for r in recs if r["library"] not in keys]
    for r in extra:
        fail(f"{page}: unexpected row for {r['library']}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
