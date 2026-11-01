# cloud-switch

This sample is one notes service that runs on the in-memory drivers or on
Cloudflare. You choose by configuration, and the code does not change.

The service is written against four `dev.cajeta.cloud` ports. A note's text
goes to the object store. The note count goes to the key-value store. Each new
note puts a `created` event on the queue. `GET /me` needs a bearer token that
the identity provider verifies.

| Route | What it does |
|---|---|
| `POST /notes` | Stores `{"text": ...}` and answers 201 with the note's id |
| `GET /notes/{id}` | Reads a note back, or answers 404 |
| `GET /events` | Takes and acknowledges up to ten queued events and counts them |
| `GET /me` | Names the signed-in user; 401 without a valid token |

## Choosing the providers

A test or dev build runs on the memory drivers with nothing configured.
`DevProviders` names `memory` for every port in those profiles. Cloudflare's
adapters are compiled in too, so code has to settle the choice, and code wins
over the environment.

```sh
cajeta run            # a dev build on 127.0.0.1:8080, memory drivers
```

A production build has no such component, so it reads the environment. It
refuses to start, naming the setting, until every provider is named.

| Port | Variable | Memory | Cloudflare |
|---|---|---|---|
| object store | `OBJECT_STORE_PROVIDER` | `memory` | `cloudflare` (R2) |
| queue | `QUEUE_PROVIDER` | `memory` | `cloudflare` (Queues) |
| key-value | `KV_PROVIDER` | `memory` | `cloudflare` (Workers KV) |
| identity | `IDENTITY_PROVIDER` | `memory` | `access` (Cloudflare Access) |

Cloudflare's adapters read their account and resources from the environment:

```sh
export OBJECT_STORE_PROVIDER=cloudflare QUEUE_PROVIDER=cloudflare KV_PROVIDER=cloudflare IDENTITY_PROVIDER=access
export CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_API_TOKEN=...
export R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=notes
export CLOUDFLARE_QUEUE_ID=... CLOUDFLARE_KV_NAMESPACE_ID=...
export CLOUDFLARE_ACCESS_TEAM=your-team CLOUDFLARE_ACCESS_AUD=...
build/exe/cloud-switch-production 0.0.0.0:8080
```

`cloud-switch-production --check` makes one round trip through each selected
provider and exits. It writes, reads and deletes an object, sends, receives
and acknowledges a message, writes and reads a value, and confirms the identity
provider refuses a malformed token. Use it to check a deployment's
configuration before you serve.

The memory drivers keep nothing across a restart, and a production build has
to name them explicitly for that reason.

## Testing

```sh
cajeta test
```

The test task builds the production server, a fake Cloudflare server and the
self-test, and the self-test runs the sample both ways.

1. In its own process, a test build serves the notes routes on the memory
   drivers. `GET /me` is refused without a token and served with one that the
   memory pool issued.
2. The production build with no provider named refuses to start.
3. The production build's `--check` runs with environment variables alone
   naming Cloudflare's adapters. It runs against the testkit's
   `FakeCloudflareServer` in a separate process, which answers R2, Queues,
   Workers KV and the Access certificate set on a local port.
   `CLOUDFLARE_API_BASE_URL`, `R2_ENDPOINT` and `CLOUDFLARE_ACCESS_CERTS_URL`
   point the adapters at it.

Access signs its tokens with RS256, and no RS256 signer exists in Cajeta yet.
So the Cloudflare leg checks that Access refuses a malformed token, and
cajeta-cloud-cloudflare's own tests verify a valid one against a fixed clock.
Behind Access, a request carries its token in `Cf-Access-Jwt-Assertion`.
primavera's `WebSecurity` reads `Authorization: Bearer`, so a deployment
behind Access forwards the assertion in that header.
