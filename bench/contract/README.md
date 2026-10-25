# The service contract

Every server in this benchmark, primavera's and each competitor's, implements
this contract exactly. Before any load, `check.py` sends every probe in
`probes.tsv` and compares the answer with the golden file next to it; a
server that differs gets no measured row. The shape is the register-user
sample's (`samples/register-user`): a JSON `POST /users` through dependency
injection, request scope, validation and an authentication filter.

## `GET /health`

`200`, `Content-Type: application/json`, body `{"status":"up"}`. Not behind the
filter. The cold-start and RSS rows poll it.

## `POST /users`

1. **Authentication filter.** A filter (Spring `OncePerRequestFilter`, a
   JAX-RS `ContainerRequestFilter`, a Micronaut `HttpServerFilter`, ASP.NET
   middleware, an ASGI middleware, a primavera pipeline stage) runs before the
   handler and admits the request only when the `Authorization` header is
   exactly `Bearer bench-7f3c9a1e`. Anything else, the header missing
   included, is answered by the filter: `401`, body `{"error":"unauthorized"}`.
   The filter guards `/users` only.
2. **Request scope.** On admission the filter stores the principal
   `bench-client` in a request-scoped component (Spring `@RequestScope`,
   CDI `@RequestScoped`, Micronaut `@RequestScope`, `AddScoped`, a
   per-request dependency, a primavera `@Component(scope = "Request")`
   provided by the stage). The handler reads it from there, not from the
   header.
3. **Dependency injection.** The handler is wired to a singleton
   `UserService`, which is wired to a singleton `IdMinter`.
4. **Validation**, in this order, the first failure answering `400` with
   body `{"error":"<message>"}`:

   | Rule | Message |
   |---|---|
   | `username` present and a string | `username is required` |
   | `password` present and a string | `password is required` |
   | `username` 3 to 64 characters | `username must be 3 to 64 characters` |
   | `password` at least 8 characters | `password must be at least 8 characters` |

   Use the framework's own validation where it has one (Jakarta Bean
   Validation, DataAnnotations, pydantic), mapped to these bodies. Characters
   are UTF-16 code units in Java and C# and code points in Python and
   primavera; every probe is ASCII, where they agree.
5. **Answer** `201`, `Content-Type: application/json`, body (no whitespace,
   members in this order):

   ```json
   {"id":"u-c3e35d3f","username":"ada_lovelace","confirmed":false,"registeredBy":"bench-client"}
   ```

   `id` is `u-` and the 32-bit FNV-1a of the username's UTF-8 bytes in eight
   lowercase hex digits (offset basis `0x811c9dc5`, prime `16777619`),
   minted by `IdMinter`. `registeredBy` is the request-scoped principal.
   Nothing is stored: database shapes wait on a primavera data layer
   (benchmark-reference spec §12.5), so the same body can be sent under load.

## `GET /fortunes`

`200`, `Content-Type: text/html; charset=utf-8`. A singleton
`FortuneRepository` holds the twelve rows of `fortunes.json`; per request the
handler takes them, sorts them by message (code-unit order, `Ordinal` in
.NET), and renders them through the framework's template engine
(cajeta-jinja, Thymeleaf, Qute, Razor, Jinja2) with HTML escaping on. The
markup is `fortunes.jinja` rendered by Jinja2: `fortunes-200.html`, one line,
no trailing newline. Micronaut has no row on this page, as the page says.

The comparison canonicalizes equivalent character references (`&quot;` and
`&#34;`, `&#x27;` and `&#39;`, numeric references to non-ASCII characters)
and nothing else; see `check.py`.

## Running a server

Each server binds `127.0.0.1` on the port it is given, logs nothing per
request, and runs as one process (uvicorn with one worker). The launch
command, the clean and build commands and the pinned version of each are in
`competitors/apps.tsv`.
