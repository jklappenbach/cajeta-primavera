# Request scope

primavera publishes the `Request` scope: `Requests.run(body)` is one request,
and a component that names the scope is built once per request and freed when
`run` returns or throws. `WebServer` runs every request through it.

```cajeta
import cajeta.aot.Component;
import dev.cajeta.primavera.context.Requests;

@Component(scope = "Request")
public class Cart {
    public Cart() { return; }
}

Requests.run(() -> {
    Cart a = Cart.__cajeta_inject();
    Cart b = Cart.__cajeta_inject();   // the same instance
});                                    // freed here
```

The compiler owns the scope: the anchor is `Requests.run`, marked
`@Scope("Request")`, and the language's component model does the rest. The
rules are the language's (guide chapter 19, "Scopes"):

- An injection outside every request throws `ScopeNotActiveException`.
- A value the program produces, rather than the graph, is placed with
  `Components.provide(#value)`. The pipeline provides its `RouteMatch` and
  `JsonBody` this way, and the handler stage injects them.
- A task spawned inside a `scope { }` block shares the request.
- A detached task, or one handed a `FiberContext`, sees no request. It takes
  what it needs as owned arguments.
