# primavera

An opinionated enterprise framework for [Cajeta](https://github.com/jklappenbach/cajeta) —
roughly what Spring is to Java. primavera is built **on** the language's core DI
substrate (`@Component`, `@Inject`, `@Factory`, the compile-time graph) and neutral
primitives (`FiberLocal`, reflection); it ships **policy** — request/session scope,
stereotypes, deployment profiles, and (coming) a web request/session model — so the
core language stays small and other frameworks remain free to innovate their own
patterns.

> **Why a separate library?** Cajeta the *language* ships the DI **substrate** —
> `@Component`/`@Inject`/`@Factory`, the graph, scopes, and lifecycle (one
> indivisible mechanism; see the stdlib `docs/specification/lang/AspectModel.md`) —
> plus ambient per-request state (`FiberLocal`) and reflection. primavera ships an
> *opinion* about how to assemble those into enterprise services. If primavera's
> opinion isn't yours, you keep the substrate and build your own — nothing in the
> core forces primavera on you.

## Status — v0.5.0

| Capability | State |
|---|---|
| **`Request` and `Session` scopes**, published for `@Component(scope = ...)` (`Requests`, `SessionEntry`) | ✅ built, self-tested |
| DI substrate (`@Component` / `@Inject` / `@Factory` / aspects) | ↳ **core stdlib** — primavera consumes it (`docs/specification/lang/AspectModel.md`) |
| Session store with idle and absolute TTLs (`SessionScope`, `SessionStore`); store-issued ids with an OPEN / GONE / UNKNOWN lookup, a capacity, an eviction observer, and a sweep while serving | ✅ built, self-tested |
| **Web**: the HTTP pipeline over [cajeta-http](https://github.com/jklappenbach/cajeta-http), routing, binding, WebSocket endpoints with open and close hooks and a send queue bounded in bytes, codecs and codings, static directory mounts ([`docs/Web.md`](docs/Web.md)) | ✅ shipped, self-tested, exercised by the register-user sample |
| **Security**: bearer tokens from the [cajeta-cloud](https://github.com/jklappenbach/cajeta-cloud) identity port, the policy algebra, startup coverage of every route, challenge handles ([`docs/Security.md`](docs/Security.md)) | ✅ shipped, self-tested; RS256 and ES256 verified, ES256 from the memory driver, request scope only (limits in the page) |
| Stereotypes (`@Repository` / `@Service`) + deployment `@Profile` | ▢ planned (policy over the core substrate) |
| primavera-side unit-test helpers (`PrimaveraTest`) | ✅ built, self-tested (on [cajeta-unit](https://github.com/jklappenbach/cajeta-unit)) |

See [`plan/README.md`](plan/README.md) for where the roadmap lives.

## Request and session scopes

primavera publishes two scopes for the language's component model. A component
names one, and the compiler builds one instance per scope and frees it at the
scope's end:

```cajeta
import cajeta.aot.Component;
import dev.cajeta.primavera.context.Requests;

@Component(scope = "Request")
public class Cart {
    public Cart() { return; }
}

Requests.run(() -> {
    Cart a = Cart.__cajeta_inject();
    Cart b = Cart.__cajeta_inject();   // the same Cart: one per request
});                                    // the Cart is freed here, on return or throw
```

`WebServer` runs every request through `Requests.run`. A `Session` component
lives in the session the request is attached to (`SessionScope.attach`), so a
later request of the same session gets the same instance, and it is freed when
the session is invalidated or expires.

A task spawned inside a `scope { }` block shares the request. A detached task,
or one handed a `FiberContext`, sees no request and takes what it needs as owned
arguments.

## Build & test

Requires the Cajeta toolchain on `PATH` (or invoke the versioned binary
directly):

```
cajeta build    # compile to build/archive/dev.cajeta.primavera-<version>.cja
cajeta test     # build + run the runtime self-tests (fails the build on any failure)
```

## Documentation

- [`docs/specification/primavera-spec.md`](docs/specification/primavera-spec.md) — **the canonical framework specification** (scopes, config, web/endpoints, resilience, security, data, observability, …).
- [`docs/RequestScope.md`](docs/RequestScope.md) — the `Request` scope: anchor, lifetime, fibers.
- [`docs/Pipeline.md`](docs/Pipeline.md) — the processing pipeline: stages, kinds checked at build, buffers in and out, throw on error.
- [`docs/Configuration.md`](docs/Configuration.md) — config & value injection (`@Value`/`@Config`): sources, AoT binders, frozen-mode, secrets, ML experiment config.
- [`docs/Data.md`](docs/Data.md) — multi-store data access (SQL/DynamoDB/Redis): the neutral annotation union, generated repositories, per-store dialects.
- [`docs/Connections.md`](docs/Connections.md) — connections, presence & addressing: the scope hierarchy, connection-as-actor, `ConnectionRegistry`, protocol capability matrix (scales via cajeta-cluster).
- [`docs/AspectModel.md`](docs/AspectModel.md) — pointer: the component model + AOP substrate is **core stdlib**; primavera adds the policy layer on top.
- [`docs/Factory.md`](docs/Factory.md) — `@Factory` design rationale (normative spec is the stdlib): third-party types, assisted args, init-beyond-ctor.
- [`docs/Testing.md`](docs/Testing.md) — how DI overrides work under test: the four override layers + scope seeding.
- [`docs/specification/EnterpriseFrameworkLandscape.md`](docs/specification/EnterpriseFrameworkLandscape.md) — comparative analysis of Spring & competitors; what primavera takes on, defers, or cedes.
- [`plan/README.md`](plan/README.md) — where the roadmap lives.

## License

Apache-2.0.
