package bench.web;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;
import java.util.List;
import java.util.Map;

/** The first failing rule, in the contract's order, as {"error": message}. */
@Provider
public class ValidationMapper implements ExceptionMapper<ConstraintViolationException> {
    private static final List<String> ORDER = List.of(
            "username is required", "password is required",
            "username must be 3 to 64 characters", "password must be at least 8 characters");

    @Override
    public Response toResponse(ConstraintViolationException e) {
        String first = null;
        int best = Integer.MAX_VALUE;
        for (ConstraintViolation<?> v : e.getConstraintViolations()) {
            int i = ORDER.indexOf(v.getMessage());
            if (i >= 0 && i < best) {
                best = i;
                first = v.getMessage();
            }
        }
        return Response.status(400).type(MediaType.APPLICATION_JSON_TYPE)
                .entity(Map.of("error", first == null ? "invalid request" : first)).build();
    }
}
