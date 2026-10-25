package bench.web;

import jakarta.inject.Inject;
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerRequestFilter;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.Provider;
import java.nio.charset.StandardCharsets;

/** Guards /users: admits only `Bearer bench-7f3c9a1e` and stores the principal. */
@Provider
public class AuthFilter implements ContainerRequestFilter {
    private static final byte[] UNAUTHORIZED = "{\"error\":\"unauthorized\"}".getBytes(StandardCharsets.UTF_8);

    @Inject
    Principal principal;

    @Override
    public void filter(ContainerRequestContext ctx) {
        if (!"/users".equals(ctx.getUriInfo().getPath())) {
            return;
        }
        if (!"Bearer bench-7f3c9a1e".equals(ctx.getHeaderString("Authorization"))) {
            ctx.abortWith(Response.status(401).type(MediaType.APPLICATION_JSON_TYPE).entity(UNAUTHORIZED).build());
            return;
        }
        principal.setName("bench-client");
    }
}
