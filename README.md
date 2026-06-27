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

## Status — v0.1.0 (early)

| Capability | State |
|---|---|
| **Request scope** over `FiberLocal` (`RequestScope`, `ScopeMap`) | ✅ built, self-tested |
| DI substrate (`@Component` / `@Inject` / `@Factory` / aspects) | ↳ **core stdlib** — primavera consumes it (`docs/specification/lang/AspectModel.md`); not owned here |
| Session scope (`SessionScope` + a session store) | ▢ designed, next increment |
| Web request/session model + `@RestServer` (policy over [cajeta-http](https://github.com/jklappenbach/cajeta-http)) | ▢ planned |
| Stereotypes (`@Repository` / `@Service`) + deployment `@Profile` | ▢ planned (policy over the core substrate) |
| primavera-side unit-test helpers (mock `@Request`/`@Session`, both executors) | ▢ planned (builds on [cajeta-unit](https://github.com/jklappenbach/cajeta-unit)) |

See [`plan/primavera-plan.md`](plan/primavera-plan.md) for the roadmap.

## Request scope

The load-bearing idea: request-scoped state is keyed on the **logical request**,
not on a thread or fiber. Because it rides a `FiberLocal` binding, one mechanism
serves both webserver concurrency models:

- **thread / fiber-per-request** — the request owns one fiber start to finish,
  so the scope *is* that fiber's binding. Cajeta's cheap fibers make this scale
  where OS-thread-per-request can't.
- **threadpool over completion ports** (epoll / io_uring / IOCP) — the request
  isn't pinned to a thread; its continuation hops pool threads as I/O completes.
  A thread-local bag would be a correctness bug here. The scope travels *with*
  the request — structured fan-out inherits the binding, an unstructured handoff
  carries it via a `FiberContext` snapshot — so it follows the request across
  thread hops and never leaks across requests.

```cajeta
import dev.cajeta.primavera.context.RequestScope;

RequestScope.enter(() -> {
    // current() is live for the whole call tree — no parameter threading.
    if (RequestScope.has("com.app.Cart") == false) {
        RequestScope.store("com.app.Cart", #(heap Cart()));
    }
    Cart cart = (Cart) RequestScope.lookup("com.app.Cart");
    handle(request, cart);
});   // the bag — and every bean it owns — drops here
```

The bag (`ScopeMap`) **owns** its beans: when the request ends, the whole graph
of request-scoped instances drops with it.

## Build & test

Requires the Cajeta toolchain on `PATH` (or invoke the versioned binary
directly):

```
cajeta build    # compile to build/archive/dev.cajeta.primavera-<version>.cja
cajeta test     # build + run the runtime self-tests (fails the build on any failure)
```

## Documentation

- [`docs/specification/primavera-spec.md`](docs/specification/primavera-spec.md) — **the canonical framework specification** (scopes, config, web/endpoints, resilience, security, data, observability, …).
- [`docs/RequestScope.md`](docs/RequestScope.md) — request scope: model, ownership, concurrency.
- [`docs/Configuration.md`](docs/Configuration.md) — config & value injection (`@Value`/`@Config`): sources, AoT binders, frozen-mode, secrets, ML experiment config.
- [`docs/Data.md`](docs/Data.md) — multi-store data access (SQL/DynamoDB/Redis): the neutral annotation union, generated repositories, per-store dialects.
- [`docs/Connections.md`](docs/Connections.md) — connections, presence & addressing: the scope hierarchy, connection-as-actor, `ConnectionRegistry`, protocol capability matrix (scales via cajeta-cluster).
- [`docs/AspectModel.md`](docs/AspectModel.md) — pointer: the component model + AOP substrate is **core stdlib**; primavera adds the policy layer on top.
- [`docs/Factory.md`](docs/Factory.md) — `@Factory` design rationale (normative spec is the stdlib): third-party types, assisted args, init-beyond-ctor.
- [`docs/Testing.md`](docs/Testing.md) — how DI overrides work under test: the four override layers + scope seeding.
- [`docs/specification/EnterpriseFrameworkLandscape.md`](docs/specification/EnterpriseFrameworkLandscape.md) — comparative analysis of Spring & competitors; what primavera takes on, defers, or cedes.
- [`plan/primavera-plan.md`](plan/primavera-plan.md) — roadmap.

## License

Apache-2.0.
