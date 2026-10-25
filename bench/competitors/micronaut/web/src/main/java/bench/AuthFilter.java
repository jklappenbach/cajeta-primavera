package bench;

import io.micronaut.core.annotation.Nullable;
import io.micronaut.http.HttpRequest;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.RequestFilter;
import io.micronaut.http.annotation.ServerFilter;
import java.util.Map;

/** Guards /users: admits only `Bearer bench-7f3c9a1e` and stores the principal. */
@ServerFilter("/users")
public class AuthFilter {
    private final Principal principal;

    public AuthFilter(Principal principal) {
        this.principal = principal;
    }

    @RequestFilter
    @Nullable
    public HttpResponse<?> filter(HttpRequest<?> request) {
        if (!"Bearer bench-7f3c9a1e".equals(request.getHeaders().get("Authorization"))) {
            return HttpResponse.status(HttpStatus.UNAUTHORIZED)
                    .contentType(MediaType.APPLICATION_JSON_TYPE)
                    .body(Map.of("error", "unauthorized"));
        }
        principal.setName("bench-client");
        return null;
    }
}
