# DI Request-Scope + Reflection Enablers for Testing — Spec & Plan

> Status: spec + plan (2026-06-16). Combines the `@Component` request/session
> scoping gap with the reflection enablers cajeta-unit needs, because they are
> two ends of one project: **the test framework is the primary consumer and
> validator of the request-scope DI.** Touches `cajeta-two` (compiler/runtime)
> and `cajeta-unit` (the framework). Related: [[cajeta-unit-state]],
> `plans/Sort-plan.md` style. DI docs: `docs/stdlib/AspectModel.md`,
> `docs/stdlib/Annotations.md`, `docs/stdlib/Reflection.md`.

## 0. The motivating scenario

> To test a webserver **request handler**, you (1) stand it up with its
> dependencies, (2) replace external seams (DB, HTTP) with fakes/mocks, (3)
> **enter a request/session scope and seed it**, then assert.

(1) and (2) work *today* (`@Component` + the shipped `@TestComponent`/`@Profile`).
**(3) is the gap** — the DI has no request/session scope, so there's nothing to
seed and nothing to share request-scoped state through. That gap, not test-only
annotations, is the true prerequisite for the framework's headline use case.

## 1. Current state (grounded in the code, with the doc drift called out)

**DI lifetime modes** (`@Inject(allocate = …)`, parsed at `CajetaModule.cpp:747`):

| Mode | Status | Notes |
|---|---|---|
| `ALLOCATE_SINGLETON` (default) | **works** | per-process lazy singleton; `@PreDestroy` at exit; injectees borrow a module static |
| `ALLOCATE_OWNER_SCOPE` | **works** | bound to the holding object; dropped with it |
| `ALLOCATE_TRANSIENT` | **works** | fresh per read; owned by the receiver scope |
| `ALLOCATE_CALL_SCOPE` | **STUBBED** — throws `CAJETA_ERROR_NOT_IMPLEMENTED` (`CajetaModule.cpp:~775`) | "per method activation"; R5-A' integration never reached the inject path |
| `ALLOCATE_FIBER` / request | **missing** | the gap this plan adds |
| session (identity-keyed) | **missing** | deferred; needs a session registry |

> **Doc reconciliation needed (both wrong, opposite directions):**
> `AspectModel.md` claims "the four lifetime modes … are all implemented" — but
> CALL_SCOPE is stubbed. `Annotations.md:560` claims scope is "Today implicit
> per-call-site" and `@Scope` is future — but three modes are real and
> site-declared via `@Inject(allocate=…)`. Fix both as part of this work.

**Reflection enablers** (what cajeta-unit needs):

| Enabler | Status |
|---|---|
| Static method reflective invoke | **FIXED** (branch `fix/reflect-static-invoke`): adapter now resolved from the method's RTTI, not the null receiver |
| Method/class annotation **name** reflection + `Class.allClasses()` | **works** (the earlier "inert/SIGSEGV" reading was a `valueOf` confound) |
| Reflective **newInstance** | native (`__cajeta_class_new0`/`__cajeta_class_new`) + per-class `reflect_new` adapter + RTTI `newInstanceAdapter` **all exist**; only the Cajeta-level `Class.newInstance()` API is missing → **wiring job** |
| Annotation **element-value** reflection | API **exists** (`Annotation.getArgInt/getArgString/getArgBool/getArgList*`); the spec §9 "elements not registered" claim is likely stale → **verify, don't build** |
| `@Mock` codegen (synthesize a mock impl) | **missing** — the one genuinely new compiler feature (the long pole) |
| `@TestComponent` / `@Profile` test contexts | **works** (shipped; `CajetaModule.cpp:584`) |

## 2. Spec

### 2.1 `ALLOCATE_FIBER` — request/fiber scope over `FiberLocal`

A new `@Inject(allocate = ALLOCATE_FIBER)` mode: **one instance per fiber-scoped
binding**, shared by every injection site on that fiber's request path, inherited
across structured fan-out, carried across a worker handoff, and cleaned at scope
exit. It is the per-request *and* per-thread analog (Cajeta is fiber-based), built
on the shipped `cajeta.concurrent.FiberLocal<T>` (`where`/`get`/`orElse`/
`isBound`) — the exact "request-context infrastructure" the deferred request
scope was waiting on.

**Codegen** (mirrors the existing `get_X`/`make_X` helpers, `CajetaModule.cpp:567`):
for a fiber-scoped component `X`, emit a module-level `static FiberLocal<X> __fiber_X`
and a `get_fiber_X()` that returns `__fiber_X.get()` (or lazily binds a fresh `X`
on first access within the active scope — TBD, see open questions). Injection
sites read `get_fiber_X()`.

**Entering a scope.** A component is fiber-scoped only *inside* a binding:
```cajeta
RequestScope.enter(() -> {            // binds the fiber's request scope
    handle(req);                      // every ALLOCATE_FIBER inject here shares one instance
});                                   // instances cleaned on exit (normal or throw)
```
`RequestScope.enter` is a thin stdlib wrapper over the per-component `FiberLocal`s
(or one umbrella `FiberLocal<ScopeMarker>` that gates lazy binding). Outside any
binding, an `ALLOCATE_FIBER` read either throws (`FiberLocal.get` on unbound) or
falls back per a declared policy — pin in design.

**Ownership / borrow-checker.** The `FiberLocal<X>` binding **owns** the instance
for the scope's extent; injection sites **borrow** it (same discipline as
SINGLETON, which borrows a module static). Cleanup runs on scope exit via the
binding's drop, before the borrow's lifetime ends — sound under the single-owner
model. Fan-out inheritance shares the *binding* (FiberLocal Layer 2), so the
shared instance must be safe for concurrent `get` (read-shared; mutation through
it needs the same `Mutex` discipline the logging `SystemLogEntry` uses, spec
§11).

**Session scope** is explicitly *out of scope here* (needs a keyed registry +
eviction); `ALLOCATE_FIBER` covers per-request, which is the high-value case.

### 2.2 `Class.newInstance()` — expose the existing adapter

Add to `cajeta.reflect.Class` (and/or `Constructor`):
```cajeta
public #Object newInstance();                 // no-arg ctor
public #Object newInstance(int64[] args);     // marshalled args
```
wired to `__cajeta_class_new0(this.rtti, ctorIdx)` / `__cajeta_class_new(...)`
(natives already present). This unblocks **instance `@Test` classes** (per-test
isolation) and instantiating test doubles/components reflectively. Same shape as
the static-invoke fix: the API is the only missing piece.

### 2.3 Annotation element-value reflection — verify + adopt

`Annotation.getArgInt/getArgString/getArgBool/getArgList*` exist. Verify they
return real values for a user `@interface` with elements (e.g. `@Tag("slow")`,
`@ValueSource(ints={0,-1,9})`); if so, parameterized tests, `@Disabled("reason")`,
and `@Tag` filtering are all immediately buildable in the library. If a gap
remains, it's a narrow RTTI-emission fix, not the "annotations are inert" rewrite
the stale spec implies.

### 2.4 `@Mock` codegen — the annotation-processing hook (long pole)

A compiler pass that, for a `@Mock T` field / `@GenerateMock(T.class)`, synthesizes
`Mock<T>` implementing T's interface: records invocations, matches argument
matchers (`any()/eq()/argThat()`), returns stubbed values (`when().thenReturn/
thenThrow/thenAnswer`), exposes `verify(..., times(n))`. Surface mimics Mockito;
mechanism is generated code (gomock/mockall model — runtime proxies are
impossible AOT). Registered as a `@TestComponent` so a generated mock drops into
the DI graph where the prod component was. **Until this lands, hand-written fakes
via `@TestComponent` cover the need** (and the spec prefers fakes for env seams).

### 2.5 How cajeta-unit consumes these

- **`@Test` auto-discovery** (reflective): `allClasses()` → methods annotated
  `@Test` (by name) → invoke. Static methods work *now*; instance methods + a
  fresh per-test instance once `newInstance` is wired. Lifecycle `@BeforeEach/
  @AfterEach/@BeforeAll/@AfterAll`, `@Disabled` (reason via §2.3), `@Tag`
  filtering. The runner core is unchanged from v0.1.0 — discovery just generates
  the `test(name, …)` calls, so v0.1 explicit registration is forward-compatible.
- **Test contexts**: `@TestComponent`/`@Profile` (shipped) for unit (override
  everything) vs integration (override only the external seams), per spec §6.
- **Request-handler testing**: a `withRequestScope(seed, () -> { … })` helper
  (over §2.1) lets a test enter a request scope, seed request/session state, run
  the handler, and assert — with external seams faked.
- **Mocks/fakes**: fakes now (`@TestComponent` + env fakes §2.4 of the unit
  spec); generated mocks when §2.4 lands.

## 3. Plan (dependency-ordered; each step validated by the framework)

- **P0 — land the static-invoke fix.** Merge `fix/reflect-static-invoke`
  (95/95 ReflectionTests green). *Done, on branch.*
- **P1 — cheap enablers (wiring + verify).**
  - Wire `Class.newInstance()` / `Constructor.newInstance()` to the existing
    natives; add focused reflection tests (no-arg + arg ctor, ownership).
  - Verify annotation element-value reflection on a user `@interface`; fix RTTI
    emission only if a gap surfaces.
  - Reconcile the DI docs (`AspectModel.md` CALL_SCOPE status, `Annotations.md`
    `@Scope` row).
- **P2 — `ALLOCATE_FIBER` request scope.** Add the enum + parse case
  (`CajetaModule.cpp`), the `FiberLocal<X>` holder + `get_fiber_X()` codegen, and
  the `RequestScope.enter(...)` stdlib wrapper. Tests: shared instance within a
  scope, distinct across scopes, inherited across `scope`-fan-out, cleaned on exit
  (normal + throw). *(Optionally finish `ALLOCATE_CALL_SCOPE` here — same
  machinery, narrower lifetime.)*
- **P3 — cajeta-unit `@Test` discovery + contexts (v0.2).** Reflective runner:
  discover + run `@Test` (static now), lifecycle, `@Disabled`/`@Tag`; document
  `@TestComponent`/`@Profile` flow; add `withRequestScope(...)`. Instance `@Test`
  once P1 newInstance is in.
- **P4 — environment fakes.** `FakeClock`/`MutableClock`, in-memory `@Repository`
  fake, seeded RNG — each an override at a capability seam (cajeta-unit spec §6).
- **P5 — `@Mock` codegen (long pole).** The annotation-processing pass + the
  Mockito-surface API. `@TestComponent` fakes bridge until then.
- **Acceptance (the proving sample):** a `samples/` request handler with a
  request-scoped session + a faked repository, tested end-to-end with cajeta-unit
  — exercises `ALLOCATE_FIBER`, `@TestComponent`, `@Test` discovery, assertions,
  and (P5) a mock together. This sample is the acceptance test for the whole
  stack.

## 4. Docs & tour deliverables (REQUIRED — ship with each phase)

- `docs/stdlib/AspectModel.md` — correct the lifetime-mode status table; add the
  `ALLOCATE_FIBER` semantics + ownership + the `RequestScope.enter` pattern.
- `docs/stdlib/Annotations.md` — fix the `@Scope`/allocate row; document
  `newInstance` and annotation-value reflection.
- `docs/stdlib/Reflection.md` — `Class.newInstance()` + reflective invoke of
  statics; the discovery recipe (`allClasses` → annotated methods → invoke).
- **cajeta-unit** `docs/unit-tour.md` + README — the `@Test`-discovery flow, the
  `withRequestScope` request-handler recipe, and `@TestComponent` contexts;
  `plan/unit-plan.md` Phase 2/3/4 updated.
- A **request-handler cookbook** doc walking the acceptance sample.
- cajetadoc on every new public surface.

## 5. Open questions

- `ALLOCATE_FIBER` unbound-read policy: throw vs lazy-bind-on-first-use vs
  fall-back-to-transient. Lean: lazy-bind within an active `RequestScope`, throw
  outside one (fail loud, like `FiberLocal.get`).
- One `FiberLocal` per fiber-scoped component vs one umbrella scope marker gating
  a per-scope instance map — perf vs simplicity.
- Should `@Test` stay reflection-discovered (works now, startup scan) or become
  compiler-recognized (emit a test registry, like `@Component`)? Reflection first;
  registry as a later optimization.
- Session scope: keyed registry + eviction — separate plan when demanded.
- `@Mock` matcher typing: monomorphized templates give compile-time-checked
  matchers/returns — confirm the codegen shape against the template instantiator.
