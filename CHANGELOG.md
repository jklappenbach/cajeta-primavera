# Changelog

## 0.5.0

What cabra needs to run on primavera (primavera-live-sessions). On cajeta v0.44.0,
cajeta-http 0.9.0 and dev.cajeta.crypto 0.1.0.

**Migration.** `WebSocketEndpoints.queueBound(n)`, a message count, is replaced by
`queueBytes(n)`, a byte bound in which each queued message counts its payload plus 4
bytes (1 MiB by default). `ConnectionRegistry.peakQueued()` is replaced by
`peakQueuedBytes()`. A send that would pass the bound, or one message larger than it,
returns false and closes the connection with the overflow code (1008 unless set).

Sessions:

- `SessionStore.open()` (and `SessionScope.open()`) issues a session id the store can
  account for after the session ends; `lookup(id)` answers `SessionState.OPEN`, `GONE`
  (issued here, since ended) or `UNKNOWN` (never issued here, forged ids included),
  without keeping ended sessions. `create(id)` with a caller id still works.
- `setCapacity(n)`: at capacity `open()` returns null and displaces nobody; expired,
  unswept sessions do not count; fibers opening at once never pass it.
- `setEvictionObserver((String, int32) -> void)`: called once per session that leaves the
  store, with `SessionStore.CLOSED`, `EXPIRED` or `DISPLACED`, on the removing fiber, after
  the store's lock is released and before the session's components drop.
- A served store with an idle TTL is swept on an interval (a quarter of the TTL, at most
  60 s, or `WebServerBuilder.sessionSweep(ms)`), so a vanished client frees its session.

WebSocket:

- `WebSocketEndpoints.json(path, onOpen, onMessage, onClose)`: the open hook runs once the
  connection is registered and before its first message; the close hook runs exactly once
  with the close code for every cause, before the connection's components drop. Both run
  in its `Connection` scope.
- Server shutdown aborts each connection with 1001 and waits for its close hook before the
  http drain. The peer sees an abnormal closure rather than a 1001 frame (a cajeta-http
  limit). A shutdown with a connection open or closing no longer hangs `serve`.
- Fixed: a connection that closed before its writer fiber started was freed under that
  writer, which then crashed (about 1 run in 30 of the self-tests since 0.4.0).

Web:

- `Endpoints.staticDir(prefix, dir)` serves a directory as GET and HEAD routes under one
  `RouteId`: index.html for the prefix, types by extension, 404 for a missing file, 403 for
  an escape (lexical or a symlink out), 405 for another method unless a declared route
  takes it. A declared route wins over a file, and security rules address the mount like
  any route.

## 0.4.0

Cryptography from dev.cajeta.crypto 0.1.0 (cajeta v0.43.1, http 0.9.0, cloud 0.4.0);
ES256 tokens end to end.
