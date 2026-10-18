# Security

`dev.cajeta.primavera.security` secures a web server with bearer tokens from
the `cajeta-cloud` identity port. Every route has a rule or the server does
not start, every rule names its route by identity rather than by path, and a
refused request learns nothing about why.

## Securing a server

Build a `WebSecurity` over the identity pool and the application's user
directory. Give it a rule for each route as you register the route, then hand
it to the builder:

```cajeta
Endpoints api = heap Endpoints();
WebSecurity sec = heap WebSecurity(pool, directory);
sec.grant("members", "user");
sec.requires(IdentityCapability.TOTP());

api.json("POST", "/login", (RequestView q, JsonBody b, Response r) -> Accounts.login(b, r));
sec.rule(api.last(), Policy.anyone());
api.route("GET", "/users/me", (RequestView q, Response r) -> Accounts.me(r));
sec.rule(api.last(), Policy.role("user"));

WebSocketEndpoints ws = heap WebSocketEndpoints();
ws.json("/events", (Connection c, JsonBody m) -> Events.ignore(c, m));
sec.rule(ws.last(), Policy.anyone());

WebServerBuilder b #= WebServer.builder();
b.endpoints(#api);
b.websockets(#ws);
b.guard(#sec);
WebServer web #= b.build();
```

`api.last()` and `ws.last()` return the `RouteId` of the route just
registered. Only a registration hands one out, so a rule cannot name a route
by a string the router would read differently (primavera-spec §8,
commitment 2).

The pool and the directory are borrowed and must outlive the server.
Subjects are linked under the pool's adapter name, the name its
`capabilities().adapterName()` reports.

## Startup refuses an incomplete configuration

`build()` throws `SecurityException`, and the server does not start, when:

| Configuration | Message names |
|---|---|
| a route, WebSocket paths included, has no rule | the route: `GET /admin has no security rule` |
| a route has two rules | the route |
| a rule names a route this server does not serve | the route |
| `requires(capability)` names a capability the identity driver does not declare | the capability |

There is no implicit allow, and no class of request is exempt. A public route
says so with `Policy.anyone()`.

## The pipeline

With a guard, two stages run between routing and binding:

| Stage | Consumes | Produces | Does |
|---|---|---|---|
| authentication | routed | authenticated | verifies a bearer token and provides the request's `SecurityContext` |
| authorization | authenticated | authorized | applies the matched route's policy |

Binding then consumes `authorized`, so a pipeline that binds before it
authorizes fails its build (commitment 1). A server built without a guard
binds straight after routing.

**Authentication** reads `Authorization: Bearer <token>`. The scheme compares
without case, as RFC 6750 allows. The token is verified through the pool's
`TokenVerifier` as an access token. The token's subject is then resolved
through the `UserDirectory`. The principal is the application's user id,
never the provider's subject. The token's groups map to roles through
`grant(group, role)`; the identity port never sees roles. A request with no
`Authorization` header gets an anonymous context, and the route's policy
decides.

**Authorization** answers 401 when the policy refuses an anonymous request
and 403 when it refuses a signed-in one.

## Policies

| Policy | Admits |
|---|---|
| `Policy.anyone()` | every request, signed in or not |
| `Policy.authenticated()` | any verified principal |
| `Policy.role("admin")` | a principal holding the role |
| `Policy.all(a, b)` | requests both admit |
| `Policy.any(a, b)` | requests either admits |
| `Policy.veto(base, v)` | what `base` admits, unless `v` admits it too |
| `Policy.nobody()` | nothing |

```cajeta
Policy p #= Policy.veto(Policy.any(Policy.role("user"), Policy.role("admin")), Policy.role("suspended"));
```

Role names compare as bytes, never through a locale (commitment 6).

## Inside a handler

```cajeta
SecurityContext who = SecurityContext.current();
UserRecord me #= directory.find(who.principal());
if (who.hasRole("admin")) { ... }
```

The context lives in the request scope, which is the request fiber's, so a
structured child task sees it and a detached one does not. For testing a
policy or a handler without a token, `SecurityContext.of(principal, roles)`
and `SecurityContext.anonymous()` build one directly.

## Refusals

Every 401 has the same body, `{"error":"unauthorized"}`, and a
`WWW-Authenticate: Bearer` header. Every 403 is `{"error":"forbidden"}`. The
body never distinguishes a forged token from an expired one or a missing
role from another. The log line does: each refusal is a WARN record whose
`reason` names the check that failed (`token failed the expiry check`,
`token failed the signature check`, the route and the policy). It never
carries the token. `auditTo(logger)` sends these records to a logger of your
own, such as an audit stream; otherwise they go to `WebSecurity`'s logger.

## Sign-in challenges

`ChallengeHandles` keeps the provider's challenge session on the server. A
login that answers a challenge gives the client a handle of 32 bytes from the
CSPRNG, base64url, standing for the provider's session. `take(handle)` ends
it, so a handle is good once, and it lapses after three minutes. The
register-user sample's `/login` and `/login/challenge` show the whole flow,
TOTP enrolment included.

## Limits

- **RS256 and ES256 only.** Tokens are verified through cajeta-cloud's
  identity port, which checks RS256 and ES256 over the provider's JWKS with
  `dev.cajeta.crypto` and refuses HS256. The memory driver signs ES256 under
  a per-process key pair, so the sample and its tests take the path a real
  provider's tokens take. A real provider needs its adapter
  (primavera-web spec §8.8).
- **Access tokens live until they expire.** Verification is offline, so
  logging out revokes the refresh token and the provider's session, but an
  access token already issued is accepted until its `exp`.
- **Request scope only.** The security context is per request. A principal
  scope that outlives requests, as `Connections.md` describes it, is not
  built yet.
- **Bearer tokens only.** Cookie sessions, and CSRF with them, come later
  (primavera-web spec §10.6).
