# primavera benchmarks

primavera against Spring Boot, Quarkus, Micronaut, ASP.NET Core and FastAPI:
the measurements behind the cajeta catalog's `bench/primavera/` pages
(benchmark-reference spec §7.4, plan unit 19), on the shared harness
`dev.cajeta.bench`. The five competitors are the spec's §12.4 decision;
database-backed shapes wait on a primavera data layer (§12.5).

| Page | id | What one row is |
|---|---|---|
| Rest.md | `primavera/register-user-json` | req/s of the contract's `POST /users` at 64 and 512 connections |
| Templates.md | `primavera/templated-page` | req/s of `GET /fortunes`, 12 rows through the framework's template engine |
| Startup.md | `primavera/cold-start` | exec to the first 200 from `GET /health`, 20 launches |
| Startup.md | `primavera/idle-rss` | resident set 2 s after that first 200 |
| Startup.md | `primavera/loaded-rss` | resident set after 60 s of `POST /users` at 512 connections |
| Build.md | `primavera/build-time` | a clean build to a runnable artifact |
| Di.md | `primavera/di-graph-100-startup` | exec to exit of an app that wires 100 components 10 deep and makes the first injected call |

## Run it

From this directory, with the cajeta compiler on `PATH` (or `CAJETA=`):

```sh
./bench.sh --list                              # the seven ids
./bench.sh --bench cold-start                  # primavera only
./bench.sh --bench cold-start --competitors    # primavera and every pinned competitor
./bench.sh --competitors                       # every id on every platform: the full run
cajeta bench                                   # the same full run, as a task
test/bench_smoke.sh                            # the smoke test (every id, every platform)
```

`bench.sh` builds everything first (`scripts/build-all.sh`; `--no-build`
skips it), then writes `results/<machine>/<run-id>/results.csv` and
`env.csv`, run id `<ISO-8601-basic-UTC>-<cajeta-version>`, and points
`results/<machine>/LATEST` at it. A published run refuses to start unless the
load average is under 1 (`--force` overrides; the figure goes into env.csv).
`--smoke` (or `CAJETA_BENCH_SMOKE=1`) is warmup 1 and trials 3, 3 s of load
per trial, 3 launches, one build per platform; its rows are tagged `smoke`
and land under `build/results/`, never `results/`. `--machine` sets the
`machine` column (default the hostname).

Measured smoke durations on Phoenix, 2026-10-25, on dev.cajeta.bench 0.1.5
(`test/bench_smoke.sh`, 22.0 min in all, at load average 8 to 18 from other
sessions): build-all 583 s (it rebuilt the server, 293 s, the DI app, 91 s,
and the harness, 157 s; 43 s when everything is already built),
register-user-json 151 s, templated-page 62 s, cold-start 27 s, idle-rss
77 s, loaded-rss 108 s, build-time 279 s, di-graph-100-startup 28 s.
A full run is roughly 5 × 30 s of load per
throughput row, 20 launches per cold-start row, 3 × 60 s per loaded-rss row
and 3 clean builds per build-time row: about 1.5 hours.

What it needs: Java 25 (every Maven project carries its wrapper, so the
system Maven does not matter), the .NET 10 SDK (`~/.dotnet` or `DOTNET=`),
the FastAPI venv at `../../cajeta/bench/competitors/python/.venv`
(`BENCH_PYTHON=`), `oha` (`~/.cargo/bin/oha` or `OHA=`), python3, GNU time.
The first build fetches the Maven and NuGet dependencies; every timed build
runs offline afterwards. Nothing touches the GPU.

## The contract

Every server implements [`contract/README.md`](contract/README.md): `GET
/health`; `POST /users` through an authentication filter that puts the
principal in a request-scoped component, DI-wired singletons, the
framework's validation, and a byte-exact 201; `GET /fortunes` rendered by
the framework's template engine (cajeta-jinja, Thymeleaf, Qute, Razor,
Jinja2). `contract/check.py` compares every server with the golden bytes
before any load, and a server that differs gets a failed row instead of a
number.

## Layout

| Path | |
|---|---|
| `src/main/cajeta/bench/primavera/` | the harness entry (`Main`) and one Benchmark per id |
| `apps/web`, `apps/di` | primavera's server and its DI app, each its own cajeta project |
| `competitors/<framework>/{web,di}` | the competitor apps, from each framework's current starter |
| `competitors/<framework>/apps.tsv`, `apps/apps.tsv` | per app: language, platform, pinned version, clean, build and run commands |
| `contract/` | the contract, its probes and golden bytes, `check.py` |
| `di/graph.json`, `di/generate.py` | the one DI graph and the generator that writes it for all six frameworks |
| `scripts/build-all.sh` | builds every app, capped (`BUILD_CAP`, 900 s), and writes `build/status/` |

Pinned versions: Spring Boot 4.1.2 (MVC, Thymeleaf), Quarkus 3.40.1.1 (REST
Jackson, Qute, Hibernate Validator; ArC for DI), Micronaut 5.2.3 (Netty;
`micronaut-inject` for DI), ASP.NET Core 10.0.13 (MVC with a Razor view;
Microsoft.Extensions.DependencyInjection for DI), FastAPI 0.162.0 on uvicorn
0.54.0 (one worker, asyncio and h11; Jinja2 3.1.6). The JVM apps run on
whatever `java` is on `PATH` with no flags; the row records its version.
Quarkus and Micronaut native-image rows are `skipped` until GraalVM's
`native-image` is on `PATH`; their build and run lines are already in
`apps.tsv`.

## How a row is made

Each id is one `dev.cajeta.bench` 0.1.5 Benchmark whose variants are the
platforms (`spring-boot`, `quarkus-jvm@512`, ...), and every column of every
row is the harness's:

- **identity.** The per-variant hooks answer from the key's line in
  `build/apps.tsv`: `language` and `language_version`, `library` the
  platform key and `library_version` its version, `platform` the framework
  and its version, `flags` (`apps/<app>/FLAGS` for primavera, `as shipped`
  for a competitor), and the variant column the page's label
  (`64 connections`).
- **the services.** The web ids are `ServiceBenchmark`s: the harness starts
  the server on a free port in the page's range, waits for `GET /health` to
  answer 200 (polled every 1 ms), runs the measured phase, samples the
  server's resident set from `/proc` while it runs, and stops it by its PID
  (TERM, then KILL after 5 s). The throughput ids keep one server per
  variant and byte-compare it with the contract before any load; the
  start-up ids launch a fresh one in every warmup and trial.
- **throughput.** Each oha trial reports req/s (`reportedThroughput`, unit
  `req/s`, the row's figure the median trial) and oha's latency
  (`reportedStats`: min = fastest, median = p50, mean = average, p95 = p95,
  each the median over trials). The warmup's oha run is the short one
  (`isWarmup()`).
- **figures measured inside the work.** A launch row's time is exec to the
  first 200 (`reported`); a build row's is the build without its clean.
  peak_rss_kb is the median over launches of VmHWM at the first 200
  (cold-start), VmRSS 2 s later (idle-rss) or VmRSS after the load
  (loaded-rss), summed over the server and its descendants; on the
  throughput rows it is the server's VmHWM over the trials.
- **env.csv** gains every toolchain version in `build/toolchains.tsv` as
  `toolchain_<name>` (`envExtra`).

The DI rows use the library's numbers as they are: wall time of the whole
process, and peak RSS from one more run under GNU time.

What stays local: the port range (each page cycles through 50 ports from
its own base, checked with `Ports.isFree`; `Ports.free` hands out ports from
61000 up and cannot be held to a range), and the smoke build: the harness's
smoke is one warmup and three trials, so in smoke mode the build-time warmup
builds nothing and trials 2 and 3 report the first build's time (the row's
notes say so).

## Known limits

- **primavera's server is built at O0.** On cajeta 0.46.3 every optimized
  build (O1 and up, release or debug base) of a program on cajeta-http's
  server fails to link: `__cajeta_stack_cajeta_lang_Optional_<T>_drop` for
  `Optional<Dispatch>` and `Optional<Connection>` is referenced and never
  defined. The server is built on the debug base with the runtime checks off,
  and its rows say so in `flags`. Restore the release flavor in
  `apps/web/cajeta.json` (and `apps/web/FLAGS`) when it links. The DI app does
  not touch the server and is built `--release -O3 -march=native`.
- Validation counts characters (UTF-16 units in Java and C#, code points in
  Python and primavera); every probe is ASCII.
- The fortunes markup compares after canonicalizing equivalent character
  references; Razor uses a small encoder (`competitors/aspnetcore/web/
  MarkupEncoder.cs`) that escapes the same five characters as MarkupSafe.
- Ports come from 61100 to 61450, above the kernel's ephemeral range, so
  oha's client sockets cannot hold them; every server is killed by the PID
  the run recorded in `build/pids.txt`, never by name.
