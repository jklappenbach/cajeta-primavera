# primavera roadmap

primavera is Cajeta's opinionated enterprise framework — the **policy** layer over
the language's neutral **mechanism** (`@Inject`, `FiberLocal`, reflection). This
plan tracks the increments from today's request-scope foundation to a full
web/service framework with first-class testability.

## Design principle: substrate in the language, policy in primavera

The language ships the DI **substrate** and neutral primitives — one indivisible,
compiler-owned mechanism:

- `@Component` / `@Inject` / `@Factory` — declare / consume / produce nodes in the
  compile-time DI graph, with identity scopes and lifecycle. **Core stdlib**
  (`cajeta.aot`); spec at the stdlib `docs/specification/lang/AspectModel.md`.
- Aspect weaving (`@Aspect` and the advice family) — **core stdlib**.
- `FiberLocal` / `FiberContext` — ambient per-request state that propagates across
  both fan-out and handoff.
- reflection — construct + invoke by metadata.

primavera composes those into an opinion about enterprise services — request/session
scope, the web model (`@RestServer`), stereotypes, deployment profiles, and the test
harness. Anyone who dislikes the opinion keeps the substrate and builds their own
framework on the same `@Component`/`@Inject`/`@Factory` graph — the core never forces
primavera, and every library speaks one DI vocabulary with no framework dependency.

(The long-term annotation-processing / codegen extension point lets primavera or any
framework plug its *policy* — stereotypes, scopes, web — into the compiler without
core changes. It does **not** move the DI substrate out of core; the substrate is
indivisible. Tracked on the cajeta-two side.)

## Phase 1 — Request scope ✅ (shipped v0.1.0)

- `dev.cajeta.primavera.context.ScopeMap` — owning, name-keyed per-scope bean store.
- `dev.cajeta.primavera.context.RequestScope` — request scope over `FiberLocal`,
  correct under both fiber-per-request and completion-port executors.
- Runtime self-test (`selftest/SelfTest`) — enter / store / lookup / teardown.

## Phase 2 — Session scope

A session outlives a single request and is shared across a client's requests, so
it is **not** a `FiberLocal` binding. Build:

- `SessionStore` — owning, id-keyed store of session `ScopeMap`s; create / get /
  invalidate; **expiry** (idle + absolute TTL); **concurrency-safe** access
  (the store is shared across all in-flight requests — guard with the stdlib
  `Lock` / `LockGuard`; timestamps from `Clock.millisTime()`).
- `SessionScope` — ambient access to the *current* session for a request:
  bind the session **id** (cheap, owned `String`) via `FiberLocal` for the
  request extent, resolve id → store on access. The session map's lifetime is
  the store's, never the request binding's.

> **BLOCKER RESOLVED (2026-07-19, toolchain 0.9.2).** The 2026-06-16 finding —
> "cajeta collections are non-owning" — is fixed by the compiler's
> element-ownership / title-tracking program (per-slot ownership bits, `#=`
> transfer stores, drop walks that free exactly the owned slots), shipped in
> cajeta **0.9.2**. Re-verified empirically by drop-tracking under 0.9.2
> (destructor-counter fixture, `jit-run`):
> - `ArrayList<T>` **drops its `#`-transferred elements** when it drops
>   (still no `insert`/`remove` in v1).
> - `HashMap<K,V>` **owns `#`-transferred keys and values**: teardown drops
>   them, a discarded `remove(k)` drops the evicted value (no double-drop),
>   and a `put` overwrite drops the displaced value — exactly the evicting
>   primitive `SessionStore` needs.
> - The transfer is caller-spelled: `add(v)` lends, `add(#v)` transfers. An
>   owned `#T` param passed onward WITHOUT `#` drops at the callee's end while
>   the collection keeps a dangling borrow — the shape the old `ScopeMap.store`
>   had. Fixed 2026-07-19: `ScopeMap` now backs onto an owning
>   `HashMap<String, Object>` (content-keyed, owns a private key copy), and the
>   self-test asserts the bean's destructor runs at request end.
>
> Request scope is now leak-free and Phase 2 is **unblocked**. Note for the
> session store: stdlib 0.9.2 also ships `cajeta.collection.Cache<K,V>`
> (LRU + idle-TTL, expire-on-lookup + manual `evict` pass, NOT thread-safe) —
> a candidate substrate for the idle-TTL half; absolute TTL and locking still
> live in `SessionStore`.

## Phase 3 — Component lifecycle integration

- Wire request/session scope to `@Component` allocation modes so a request- or
  session-scoped component resolves through `RequestScope` / `SessionScope`
  get-or-create instead of the singleton path.
- Reconcile with the `ALLOCATE_*` modes documented in the **stdlib**
  `docs/specification/lang/AspectModel.md` (`CALL_SCOPE` is currently stubbed in
  the compiler). Request scope is the new, primavera-owned scope layered over them.

## Phase 4 — Web request/session model (policy over `cajeta-http`)

The HTTP engine is **not** primavera's — it is the
[`cajeta-http`](https://github.com/jklappenbach/cajeta-http) library
(HTTP/1.1·2·3 + WS + SSE) over the stdlib `cajeta.io.net` transport. Phase 4 is
the *policy* primavera layers on top:

- **`@RestServer` / `@Rest` endpoints** — annotation-driven routing (bind handler
  methods to verb+path) and **automatic serde** to/from a typed object model, over
  cajeta-http's imperative `HttpServer`/`Router`.
- **Request/session scope binding** — wire the request scope (Phase 1) to the
  handler boundary so request-scoped `@Component`s resolve per request.
- **Executor choice is inherited**, not reinvented: cajeta-http runs on
  `cajeta.io.net`'s accept models (fiber-per-connection / shared-pool). Scope
  propagation is correct under both (Phase 1's `FiberLocal` carries across the
  handoff; the boundary wires it in).

## Phase 5 — primavera-side unit-test helpers (on cajeta-unit)

The test capability for primavera's features lives **in primavera**, built on the neutral
[cajeta-unit](https://github.com/jklappenbach/cajeta-unit) framework but knowing
primavera's internals:

- mock `@Request` / `@Session`-scoped beans; seed request/session context.
- run a handler under a **chosen executor** (thread-per-request vs
  completion-port) so a test can assert behaviour under each.
- assert request/session **isolation** (no cross-request leakage) and that scope
  **follows the request across a handoff** — the bug a thread-per-request-only
  unit test can't see. A harness that simulates the thread-hopping
  completion-port path is what catches "someone used thread-local and it leaks
  under load."
- override the `@Inject` DI context with mocks/fakes for testing.

## Cross-cutting cleanups

- **Remove the static-field-method-receiver workaround** in `RequestScope` once
  the cajeta-two codegen bug is fixed (see project memory
  `static-field-method-receiver-segv`).
- **Once-guard** the lazy `FiberLocal` key init against a first-touch race.
- **Wire the real dependencies** (`dev.cajeta.logging` runtime, `dev.cajeta.unit`
  dev) in `cajeta.json` once they are resolvable (registry publish or
  path-dependency); primavera's web/component layer logs through cajeta-logging.

## Dependency on cajeta-two work

- A linker / build-system **dead-code-elimination** pass so a service links only
  the primavera classes it uses (embedded/robotics targets must fit an EPROM). Today
  unused classes are pinned by the reflection registry; this is tracked on the
  cajeta-two side, and primavera's per-feature modularity assumes it lands.
