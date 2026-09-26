# Pipeline

`dev.cajeta.primavera.pipeline` — the processing model of primavera-web
(spec §7.8 to §7.19, decided with Julian 2026-09-26). A `Pipeline` is an
ordered list of `Stage`s added in the order they run, checked once at
build, and driven per request. It deals in buffers in and out. No stage
calls another and no stage writes a socket.

## The contract

- **Kinds meet at build.** Each stage declares the `Kind` it consumes and
  the kind it produces. `build()` refuses a chain whose kinds do not meet,
  naming both stages, and a chain that does not start from raw bytes. A
  misordered pipeline fails on launch, never per request.
- **Buffers in, buffers out.** A stage receives a `Buffer` and returns one:
  the buffer it was handed, or one it took through `RequestContext.take()`.
  When it returns a different one, the pipeline releases the previous one.
  `Buffer` is constructible only by `BufferSource`, so every buffer in
  flight came from the pool and goes back to it. Stages borrow, the
  pipeline owns.
- **Throw on error.** A stage throws an `HttpException`, and the pipeline
  answers its `httpStatus()` with an empty body and releases whatever the
  stage took. Success is never thrown: a stage that completes the request
  itself calls `ctx.respond(status)` and returns, and the inbound walk ends
  there.
- **Outbound is the reverse walk.** After the last inbound stage, the
  pipeline calls each stage's `outbound` side in reverse order, from the
  stage that ran last back to the first. A coding decodes on the way in
  and encodes on the way out; most stages pass the buffer through.
- **State goes through the scopes.** A stage that learns something about
  the request, the principal, the media type, a decoded index, stores it
  as a request-scoped component and the stages after it resolve it there.
  Nothing travels stage to stage but the buffer.

```cajeta
BufferSource source = heap BufferSource(65536, 64);
Pipeline p = heap Pipeline(source);
p.add(heap DecodeStage());        // RAW -> DECODED
p.add(heap RouteStage());         // DECODED -> ROUTED
p.add(heap AuthenticateStage());  // ROUTED -> AUTHENTICATED
p.build();

RequestContext ctx = heap RequestContext(source);
Buffer in #= source.take();       // filled by the transport
Buffer out = p.run(#in, ctx);     // the response body, held by ctx
int32 status = ctx.status();
ctx.close();                      // every buffer back to the source
```

HTTP and WebSocket are two pipelines. A connection switches from the first
to the second at the upgrade handshake, and no stage is ever added to a
live pipeline.

## Types

| Type | |
|---|---|
| `Stage` | `name()`, `consumes()`, `produces()`, `inbound(buffer, ctx)`, `outbound(buffer, ctx)` |
| `Kind` | `RAW`, `DECODED`, `ROUTED`, `AUTHENTICATED`, `BOUND`, and `name(kind)` |
| `Pipeline` | `add(#stage)`, `build()`, `stageCount()`, `run(#input, ctx)` |
| `RequestContext` | `take()`, `respond(status)`, `responded()`, `status()`, `held()`, `close()` |
| `Buffer` | `bytes()` the `ByteBuffer`, `id()` |
| `BufferSource` | `take()`, `release(#buffer)`, `allocations()`, `idle()`, `bufferSize()` |
| `PipelineException` | a chain that cannot be built |

The standard HTTP stages and the standard pipelines arrive with the
cajeta-http buffer seam. Until then the pipeline is exercised in memory by
the self-test, which proves the kinds check, the buffer accounting across
runs and on a throw, the status mapping, the early response and the reverse
walk.
