package bench;

import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Error;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Post;
import io.micronaut.http.annotation.Status;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Valid;
import java.util.List;
import java.util.Map;

@Controller
public class ApiController {
    private static final List<String> ORDER = List.of(
            "username is required", "password is required",
            "username must be 3 to 64 characters", "password must be at least 8 characters");

    private final UserService users;
    private final Principal principal;

    public ApiController(UserService users, Principal principal) {
        this.users = users;
        this.principal = principal;
    }

    @Get("/health")
    public Map<String, String> health() {
        return Map.of("status", "up");
    }

    @Post("/users")
    @Status(HttpStatus.CREATED)
    public Account register(@Valid @Body Signup body) {
        return users.register(body, principal.getName());
    }

    /** The first failing rule, in the contract's order, as {"error": message}. */
    @Error(exception = ConstraintViolationException.class)
    public HttpResponse<Map<String, String>> invalid(ConstraintViolationException e) {
        String first = null;
        int best = Integer.MAX_VALUE;
        for (ConstraintViolation<?> v : e.getConstraintViolations()) {
            int i = ORDER.indexOf(v.getMessage());
            if (i >= 0 && i < best) {
                best = i;
                first = v.getMessage();
            }
        }
        return HttpResponse.badRequest(Map.of("error", first == null ? "invalid request" : first));
    }
}
