package bench.web;

import io.quarkus.qute.Template;
import io.quarkus.qute.TemplateInstance;
import jakarta.inject.Inject;
import jakarta.validation.Valid;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

@Path("/")
public class Api {
    @Inject
    UserService users;

    @Inject
    Principal principal;

    @Inject
    FortuneRepository repository;

    @Inject
    Template fortunes;

    @GET
    @Path("health")
    @Produces(MediaType.APPLICATION_JSON)
    public Map<String, String> health() {
        return Map.of("status", "up");
    }

    @POST
    @Path("users")
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response register(@Valid Signup body) {
        return Response.status(201).entity(users.register(body, principal.getName())).build();
    }

    @GET
    @Path("fortunes")
    @Produces(MediaType.TEXT_HTML)
    public TemplateInstance fortunes() {
        List<Fortune> rows = new ArrayList<>(repository.findAll());
        rows.sort(Comparator.comparing(Fortune::message));
        return fortunes.data("fortunes", rows);
    }
}
