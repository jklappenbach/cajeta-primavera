# Web endpoints

`dev.cajeta.primavera.web` serves typed endpoints over `cajeta-http`. A request
is read once into the connection's pooled input buffer, and an endpoint reads
it in place. Nothing is copied until the endpoint asks for a copy, and the
copy is named at the call site.

## The model

Each request runs a pipeline of stages under a fresh request scope:

| Stage | Consumes | Produces | Does |
|---|---|---|---|
| routing | raw | routed | matches an endpoint, binds path parameters, or answers 404, 405 or 413 |
| binding | routed | bound | indexes a JSON body in place for a JSON endpoint |
| handler | bound | bound | calls the endpoint with its bound values |

A `WebServerBuilder` held in a local adds stages ahead of these with `stage(...)`. Content coding
joins with the codec phase and authentication with the security phase. A
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

## The sample

`samples/register-user` registers, looks up and confirms users against the
identity port's memory driver. The application mints its own user id, and
the `UserDirectory` in `dev.cajeta.primavera.identity` keeps the provider's
subject as a link. `cajeta test` at the repo root runs it after the library's
own tests.
