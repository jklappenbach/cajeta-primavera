# Session scope

primavera publishes the `Session` scope. A session outlives any single request
and is shared across a client's requests until it is invalidated or expires. A
component that names the scope is built once per session, reached from any
request attached to that session, and freed when the session ends. In the scope
hierarchy (`docs/Connections.md`): `Message ⊂ Connection ⊂ Session ⊂ Principal
⊂ Application`.

```cajeta
@Component(scope = "Session")
public class Preferences {
    public int32 count;
    public Preferences() { this.count = 0; return; }
}

SessionScope.create("sess-1");                 // at login
SessionScope.attach("sess-1", () -> {
    Preferences p = Preferences.__cajeta_inject();
    p.count = p.count + 1;                     // kept for the next request
});
```

## The state lives in the store, the id rides the request

- **`SessionStore`** (process-wide) owns the sessions: an id-keyed map of
  `SessionEntry`, with TTL expiry and locking. Each entry is the `Session`
  anchor (`@Scope("Session")` on the class), so the components built for a
  session belong to its entry and are freed with it.
- **`SessionScope.attach(id, body)`** binds the session **id** for the
  request's extent and runs `body` with that session's entry current. An id
  with no live session runs `body` sessionless, where a `Session` injection
  throws `ScopeNotActiveException`.

## API

`dev.cajeta.primavera.context.SessionScope` (all static):

| Method | Effect |
|---|---|
| `configure(idleTtlMillis, absoluteTtlMillis)` | set the store's TTLs (0 disables either) |
| `create(String id)` | create the session, e.g. at login; an existing session under `id` is displaced and freed |
| `invalidate(String id)` | free the session and its components, e.g. at logout |
| `evictExpired()` | sweep expired sessions; returns the evicted count |
| `invalidateAll()` | free every session; returns the count |
| `sessionCount()` | sessions currently in the store |
| `attach(String id, () -> void body)` | run `body` as a request of that session |
| `isActive()` | an id is attached AND the store holds a live session for it |

`SessionStore` is also usable directly: `create/resolve/invalidate/evictExpired/count`,
plus `createAt/resolveAt/evictExpiredAt(…, int64 now)` forms that take the
timestamp explicitly, so tests drive expiry without sleeping. `resolve` returns
the `SessionEntry`, and `entry.within(body)` runs `body` with it current.

## Expiry

Two independent TTLs, both disabled at 0:

- **idle** — expires when `now - lastAccessed` exceeds it; every resolve
  refreshes the clock.
- **absolute** — expires when `now - createdAt` exceeds it, regardless of
  activity (caps session lifetime even for a busy client).

Enforcement is lazy on `resolve` — an expired session reads as absent and is
evicted on the spot — **plus** the `evictExpired` sweep, so an idle server
still frees stale sessions. Call it periodically.

## Ownership & lifecycle

The store owns its entries, and each entry anchors its session's components.
Every eviction path (idle or absolute expiry, the sweep, `invalidate`, and
`create` displacing an existing id) drops the entry and frees its components.
`attach` ending frees nothing; the session persists.

## Concurrency

The store is shared across all in-flight requests; every operation takes the
internal `Lock` (fibers park; carriers don't block). What the lock does NOT
cover: the `SessionEntry` a resolve hands back is a borrow of store state, valid
until that session is invalidated or expires. v1 posture: invalidating a
session that another in-flight request is actively using is a
caller-coordination bug — the web tier serializes a session's requests or
defers invalidation to request end.

## v1 limitations

- **Invalidate-while-in-use** is caller-coordinated (above).
- **Sweep scheduling** is the application's.
