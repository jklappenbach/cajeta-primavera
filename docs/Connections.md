# Connections, presence & addressing

The model frameworks forgot: the **live connection** as a first-class, stateful,
**addressable** entity — unified across HTTP, WebSocket, raw TCP, and UDP. Deep-dive
for `primavera-spec.md` §3 (scopes). The single-node model here scales unchanged to a
fleet via [`cajeta-cluster`](https://github.com/jklappenbach/cajeta-cluster) (§10).

## The gap

Frameworks ship **request scope** (one-shot) and **session scope** (identity, across
requests). Missing is the level between, and the primitive that reaches it:

- a **connection scope** — state that lives exactly as long as the socket, shared by
  the messages on it, dropped on close; and
- a **registry** that can answer *"who's connected, and how do I reach that one to
  push to it?"*

SignalR (`Clients.User/Group`), Phoenix (Channels + Presence), Socket.io (rooms) have
pieces — all WebSocket-only, bolted-on, not DI scopes, not protocol-spanning. This
unifies connection-as-scope + connection-as-addressable-actor + presence, with sound
lifecycle, across every protocol.

## The scope hierarchy

```
Message ⊂ Connection ⊂ Session ⊂ Principal ⊂ Application
```

| Scope | Lifetime | Keyed by | Annotation |
|---|---|---|---|
| **Message** | one inbound unit (HTTP request, WS message, datagram, TCP frame) | the message | `@MessageScoped` (= request scope) |
| **Connection** | one live transport | the connection | **`@ConnectionScoped`** |
| **Session** | across connections | identity (reconnect resumes) | `@SessionScoped` |
| **Principal** | a user's *concurrent* connections (web + mobile = 1 principal) | authenticated identity | **`@PrincipalScoped`** |
| **Application** | process | — | `@Singleton` |

All five resolve through the same `FiberLocal` + registry machinery as the existing
scopes. A component declares its lifetime; the framework does get-or-create and drop
at the right boundary.

## A connection is an addressable actor

A long-lived connection is naturally a **fiber + a mailbox (`Channel` inbox) + owned
state + a stable id** — i.e. an actor. That reframes "reach a connection" into the
solved "send to its address." Cajeta's cheap fibers make connection-per-actor scale
(the WhatsApp/Discord proof). The new part: it's a **DI scope and a registry entry at
once**.

```cajeta
@ConnectionScoped class PlayerState { int32 score; ... }   // owned; lives for the connection

@WebSocket("/play")
Stream<Update> play(in: Stream<Move> moves, @Connection Conn c, @Inject PlayerState s) {
    // c.id(), c.attr("region"), c.tell(msg) — enqueue to this connection's inbox
    // s is this connection's state, get-or-created, dropped on close
}
```

## ConnectionRegistry — address by topology, not socket ids

The registry is a **queryable index over connection metadata** — reach connections by
*what they are*, not an opaque handle. Presence, pub/sub, and routing become one
registry queried different ways:

```cajeta
@Inject ConnectionRegistry conns;

conns.to(Principal(userId)).send(event);                    // all of a user's connections
conns.to(Topic("room:42")).send(msg);                       // a subscription topic
conns.where(c -> c.attr("region") == "us-east").send(x);    // a predicate
conns.to(Multicast("239.0.0.1:9000")).send(dgram);          // protocol-appropriate target
conns.presence(Topic("room:42"));                           // "who's here" — presence IS a query
conns.subscribe(c, Topic("room:42"));                       // join a topic
```

`Target` = `Conn(id)` | `Principal(id)` | `Topic(name)` | a predicate | `Multicast(group)`.

## Ownership makes presence *sound* (the always-buggy part elsewhere)

Connection registries everywhere accrue **stale entries** (the connection died, the
entry didn't). Here the connection fiber **owns** its handle; the registry holds a
**borrowed/weak handle**, so on connection drop the registry entry **auto-deregisters
via the drop chain.** No stale connections, no manual cleanup, no leak — *enforced by
the type system*. Correct presence by construction.

## Backpressure-aware delivery

Pushing to a slow consumer is the classic broadcast footgun. Delivery rides bounded
channels (the `Stream<T>` model), so addressing a slow connection applies backpressure
or a declared per-connection overflow policy:

```cajeta
conns.to(Topic("room:42")).policy(OverflowPolicy.DROP_OLDEST).send(x);  // or BLOCK / DROP_NEWEST / CLOSE
```

## Protocol-appropriate capabilities + compile-time guardrails

One uniform model; each protocol declares what it supports; unsupported ops are
**compile errors** (same discipline as the data dialects):

| Protocol | Stateful conn | Addressable | Pushable | Duplex |
|---|:--:|:--:|:--:|:--:|
| HTTP req/resp | ✗ (per-message) | ✗ | ✗ | ✗ |
| HTTP + SSE | ✓ (while streaming) | ✓ | ✓ (one-way) | ✗ |
| WebSocket | ✓ | ✓ | ✓ | ✓ |
| Raw TCP | ✓ | ✓ | ✓ | ✓ |
| UDP unicast | synthesized *flow* (peer + idle TTL) | by address | ✓ (datagram) | ✓ |
| UDP multicast | group membership | the group | ✓ (fan-out) | ✗ |

`conns.to(c).send(...)` where `c` is a plain HTTP request/response **won't compile**.
The connectionless cases (UDP) get a **synthesized flow scope** keyed by peer address
with idle expiry — connection semantics exactly where they're meaningful.

## State migration across the hierarchy

The "resume after a dropped connection" pattern everyone hand-rolls, made declarative:

```cajeta
@ConnectionScoped(onDisconnect = PROMOTE_TO_SESSION) class Draft { ... }
```

Connection-scoped state demotes to session on disconnect and rehydrates on reconnect;
fleet-wide it can continue to a durable store (see cajeta-cluster §durability).

## Request/command processing flow

The handler runs with the full context injected — the message bag, the connection
actor + its state, the session/principal if identity is established — and its **return
shape** expresses the interaction (from the `Stream<T>` model):

- **request** → returns a reply;
- **command** → returns nothing / a deferred ack;
- **event/subscription** → returns `Stream<T>` (push);

and any handler may `conns.to(...).send(...)` to fan out to *other* connections.
"Deal with state" = inject the scope you need; "reach a connection" = address it.

## Going distributed (transparently)

`conns.to(...).send(...)` and `conns.presence(...)` run **identically** on one node
(in-process registry) and across a fleet — when
[`cajeta-cluster`](https://github.com/jklappenbach/cajeta-cluster) is present, the
registry becomes partitioned (sharded by user/topic hash over a gossip-built ring),
delivery routes to the owning node, and presence aggregates across the cluster. Same
code, laptop to planet. See cajeta-cluster's `cluster-spec.md`.

## Open questions

- **Connection-actor inbox** — exposed (`c.tell`) as a first-class API, or internal
  plumbing only? Lean: exposed; it's the natural send primitive.
- **`Topic` ownership** — how `Topic` here relates to the messaging/pub-sub tier
  (Tier-2) and to cajeta-cluster's topic sharding; one `Topic` concept or two layers?
- **Flow-scope (UDP) idle TTL** defaults and whether it's opt-in per endpoint.
- **Principal scope vs session scope** overlap when there's exactly one connection —
  collapse or keep distinct?
