# Web endpoints

`dev.cajeta.primavera.web` serves typed endpoints over `cajeta-http`. A request
is read once into the connection's pooled input buffer, and an endpoint reads
it in place. Nothing is copied until the endpoint asks for a copy, and the
copy is named at the call site.

## The model

Each request runs a pipeline of stages under a fresh request scope:

| Stage | Consumes | Produces | Does |
|---|---|---|---|
| coding | raw | raw | decodes a coded body, and on the way out codes the response (see Codecs and codings) |
| routing | raw | routed | matches an endpoint, binds path parameters, or answers 404, 405 or 413 |
| binding | routed | bound | indexes a JSON body in place for a JSON endpoint |
| handler | bound | bound | calls the endpoint with its bound values |

A `WebServerBuilder` held in a local adds stages ahead of these with `stage(...)`.
Authentication joins with the security phase. A
stage that throws an `HttpException`, such as one of the
`dev.cajeta.http.status` catalogue, ends the request with that status and an
empty body. Anything the handler already wrote is discarded.

```cajeta
Endpoints api = heap Endpoints();
api.json("POST", "/users", (RequestView q, JsonBody b, Response r) -> Users.register(b, r));
api.route("GET", "/users/{id}", (RequestView q, Response r) -> Users.lookup(q, r));
WebServer web #= WebServer.bind("127.0.0.1:8080", #api);
web.serve();
```

Buffers are 64 KiB unless `bufferBytes` says otherwise. The transport's pool
counts fresh buffers in `web.bufferAllocations()`. After warm-up, requests on
a keep-alive connection leave it unchanged.

## Three binding modes

| Mode | Registration | The handler gets | Cost |
|---|---|---|---|
| JSON index | `api.json(...)` | a `JsonBody` over the input buffer | one structural index, no tree |
| view | `api.window(...)` | the body window, for a `view` to overlay | nothing beyond the view's checks |
| owned | `api.owned<T>(...)` | a fresh `T` decoded through `Json.parse<T>` | a copy and a decode; the buffer is free afterwards |
| codec | `api.codec(...)` | a fresh `T` decoded by the codec `Content-Type` names | as owned, in any registered media type |

A view endpoint constructs its view over the window it is handed:

```cajeta
@LittleEndian
public view Registration {
    int32  age;
    String username;
}

static void byView(RequestView q, Slice<int8> body, Response r) {
    Registration v = Registration(body);
    r.json(200).field("username", v.username).end();
}
```

## Copy out what you keep

Every window a handler sees, `q.param(...)`, `q.header(...)`,
`b.string(...)` and the view itself, points into the input buffer. The next
request on the connection overwrites that buffer. A value that must outlive
the request is copied with a reader whose name says so: `paramString`,
`headerString`, `stringCopy`. The registration sample does exactly this
before it calls the identity port:

```cajeta
String username #= b.stringCopy("username");
String password #= b.stringCopy("password");
RegistrationResult reg #= pool.register(username, password);
```

`JsonBody.string` returns the raw bytes with escapes as sent.
`stringCopy` decodes them. The library's self-test overwrites the body after
each handler returns, and checks that a copied value survives while a kept
window reads the overwritten bytes.

## Responses

`Response` writes into the output buffer directly. `json(status)` starts an
object, `field` and `fieldBool` add members with strings escaped, and `end`
closes it. `error(status, message)` writes `{"error": message}`, and
`empty(status)` sends no body.

## Codecs and codings

A codec endpoint reads its body in whichever media type the request names
and answers in whichever type `Accept` prefers. JSON is always present and
is the default. Other types come from codecs the build compiles in.

```cajeta
@Component
public final class SignupProtobuf implements MediaCodec<Signup> { ... }

@Component
public final class SampleCodecs {
    @Inject ArrayList<MediaCodec<Signup>> signups;
    @Inject ArrayList<MediaCodec<Account>> accounts;
}

SampleCodecs c = SampleCodecs.__cajeta_inject();
Codecs<Signup> in = heap Codecs<Signup>(c.signups);
Codecs<Account> out = heap Codecs<Account>(c.accounts);
api.codec("POST", "/users", heap CodecEndpoint<Signup, Account>(#in, #out,
    (RequestView q, Signup s, Reply<Account> r) -> Users.register(s, r)));
```

- A `MediaCodec<T>` is a `cajeta.wire.Encoder<T>` and `BufferEncoder<T>`
  with a media type. Declared as a component, it reaches every
  `ArrayList<MediaCodec<T>>` through the DI graph. There is no registration
  call. A contributed `application/json` codec replaces the built-in one.
- `Reply.send(status, value)` encodes in the negotiated type. A codec whose
  `sizeBound` promises the output fits writes it into a buffer from the
  pipeline's pool, so the encoding makes no array of its own. `JsonCodec`
  cannot bound its output and takes the `encode` path.
- A `Content-Type` no codec reads answers 415, and an `Accept` no codec
  meets answers 406. Both bodies name the supported types. A body its
  codec cannot read answers 400. All three happen before the handler runs.

Content codings are `cajeta-http`'s registry: gzip and deflate are always
there. A dependency adds one by declaring a `ContentCodingProvider`
component. The server registers every one it finds when it is built.

- A request whose `Content-Encoding` the registry holds is decoded into a
  pooled buffer before routing. One it does not hold answers 415 with
  `Accept-Encoding` listing the codings that are held.
- A response is coded in the coding `Accept-Encoding` prefers, once it is at
  least `compressAbove` bytes (256 unless the builder sets it; 0 codes every
  body). Images, audio, video and archives are left alone.
- An `Accept-Encoding` that refuses identity and names no held coding answers 406.

## WebSocket

A WebSocket path is a GET route on the HTTP pipeline that upgrades. After the
101 the connection runs as a `Connection`, and the HTTP pipeline is unchanged.

```cajeta
WebSocketEndpoints ws = heap WebSocketEndpoints();
ws.json("/events", (Connection c, JsonBody b) -> Feed.onMessage(c, b));

WebServerBuilder b #= WebServer.builder();
b.endpoints(#api);
b.websockets(#ws);
WebServer web #= b.build();
web.connections().broadcast("{\"registered\":\"ada\"}");
```

- Each message is a JSON index over the connection's buffer, valid during
  the handler, under the same copy-out rule as a request body. A warm
  connection reads and writes a message with no allocation.
- `Connection` is the `Connection` scope: a `@Component(scope = "Connection")`
  lives from open to close. Each message runs in a `Message` scope inside it.
- `web.connections()` addresses open connections by id (`send(id, text)`) or
  all at once (`broadcast`). A connection leaves it when it closes.
- Sends are queued and written by the connection's own writer fiber, which
  runs inside `WebServer.serve`. The queue holds `queueBound` messages (64 by
  default). A peer that falls further behind is closed with `overflowCode`
  (1008 by default), so a slow reader stalls nobody else and memory does not
  grow.
- A handler that throws closes its connection: 1007 for a body that is not a
  JSON object, 1009 for an oversized message, the code of a `CloseException`,
  and 1011 for anything else. The peer gets the code and no detail.

## The sample

`samples/register-user` registers, looks up and confirms users against the
identity port's memory driver. The application mints its own user id, and
the `UserDirectory` in `dev.cajeta.primavera.identity` keeps the provider's
subject as a link. `POST /users` takes JSON or protobuf (`cajeta-codec`'s
`Protobuf`, through two small codecs), answers in the type `Accept` prefers,
and codes every response the client accepts a coding for. The test profile
adds an `x-reverse` coding that nothing else knows about, and the self-test
negotiates it both ways. Its `/events` WebSocket path announces each
registration to every subscriber. `cajeta test` at the repo root runs it
after the library's own tests.
