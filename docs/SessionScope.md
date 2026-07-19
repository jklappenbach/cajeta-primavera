# Session scope

primavera's session scope is the per-client bag of framework-managed beans: a
session outlives any single request and is shared across a client's requests,
until it is invalidated or expires. It is the runtime that makes
session-scoped `@Component` instances possible — created once per session,
reachable ambiently from any request attached to that session, and dropped
(destructors run) when the session ends. In the scope hierarchy
(`docs/Connections.md`): `Message ⊂ Connection ⊂ Session ⊂ Principal ⊂
Application`.

## The one idea: bind the *id* to the request, keep the *state* in the store

Because a session outlives the request, session state can never live in a
request binding — a `FiberLocal`-held bag would drop when the request ends.
The design splits the two lifetimes:

- **`SessionStore`** (process-wide) owns the session state: an id-keyed map of
  session bags, with TTL expiry and locking. This is the only owner; a bag
  lives exactly as long as its store entry.
- **`SessionScope.attach(id, body)`** binds only the session **id** — a cheap
  owned `String` copy — via `FiberLocal` for the request's dynamic extent.
  Every accessor resolves id → store *at access time*; nothing session-owned
  is ever cached in the request. The id binding inherits `RequestScope`'s
  propagation story: correct under both fiber-per-request and completion-port
  executors, because the binding rides the logical request.

The web tier (Phase 4, over cajeta-http — currently deferred) will read the id
from the transport (cookie / token) and wrap the handler in `attach`; handler
code anywhere on the call path uses the static accessors with no parameter
threading.

## API

`dev.cajeta.primavera.context.SessionScope` (all static):

| Method | Effect |
|---|---|
| `configure(idleTtlMillis, absoluteTtlMillis)` | set the store's TTLs (0 disables either) |
| `create(String id)` | create the session — e.g. at login; an existing session under `id` is displaced and dropped |
| `invalidate(String id)` | drop the session and all its beans — e.g. at logout |
| `evictExpired()` | sweep expired sessions; returns the evicted count |
| `sessionCount()` | sessions currently in the store |
| `attach(String id, () -> void body)` | run `body` with `id` bound as the current session |
| `isActive()` | an id is attached AND the store holds a live session for it |
| `has(String typeName)` | whether a bean is bound in the current session |
| `lookup(String typeName)` | the bean for `typeName`, or null |
| `store(String typeName, #Object instance)` | bind `instance`, session takes ownership; throws when sessionless |
| `materialize(String typeName, () -> #Object factory)` | create-and-store via `factory` iff unbound (see below) |

`SessionStore` is also usable directly (the scope's static store is not
exposed): `create/resolve/invalidate/evictExpired/count`, plus deterministic
`createAt/resolveAt/evictExpiredAt(…, int64 now)` forms that take the
timestamp explicitly — the self-tests drive expiry with a synthetic clock, no
sleeping.

## Expiry

Two independent TTLs, both disabled at 0:

- **idle** — expires when `now - lastAccessed` exceeds it; every resolve
  refreshes the clock.
- **absolute** — expires when `now - createdAt` exceeds it, regardless of
  activity (caps session lifetime even for a busy client).

Enforcement is lazy on `resolve` — an expired session reads as absent and is
evicted on the spot — **plus** the `evictExpired` sweep, so an idle server
still frees stale sessions. Scheduling the periodic sweep belongs to the
Phase-4 executor; until then call it opportunistically.

## Ownership & lifecycle

The store owns everything transitively: `HashMap<String, SessionEntry>` owns
its entries (toolchain >= 0.9.2 element ownership), each `SessionEntry` owns
its `ScopeMap`, and the `ScopeMap` owns its beans. So every eviction path —
idle/absolute expiry, the sweep, `invalidate`, and `create` displacing an
existing id — drops the whole bag graph: bean destructors run, nothing leaks.
`attach` ending drops only the id binding; the session persists.

The get-or-create resolution path for a session-scoped component is the
`materialize` + `lookup` pair:

```cajeta
SessionScope.materialize(key, () -> { return #(heap CartService()); });
CartService cart = (CartService) SessionScope.lookup(key);
```

(Two calls, not one returning the bean: a multi-parameter function may not
return a borrow — `CAJETA_ERROR_BORROW_RETURN_MULTI_PARAM` — so the borrow
comes from the single-param `lookup`.)

## Concurrency

The store is shared across all in-flight requests; every operation takes the
internal `Lock` (fibers park; carriers don't block). What the lock does NOT
cover: the `ScopeMap` a resolve hands back is a borrow of store state, valid
until that session is invalidated or expires. v1 posture: invalidating a
session that another in-flight request is actively using is a
caller-coordination bug — the web tier serializes a session's requests or
defers invalidation to request end.

## v1 limitations

- **First-touch race** on the lazy static init (`STORE`, `ID`) — shared with
  `RequestScope.SCOPE`; benign on the single-carrier cooperative scheduler,
  wrong under multi-carrier parallelism. Tracked in `plan/primavera-plan.md`.
- **Invalidate-while-in-use** is caller-coordinated (above).
- **Sweep scheduling** is manual until the Phase-4 executor exists.
