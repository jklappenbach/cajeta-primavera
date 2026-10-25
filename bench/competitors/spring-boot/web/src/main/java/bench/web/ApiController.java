package bench.web;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    private final UserService users;
    private final Principal principal;

    public ApiController(UserService users, Principal principal) {
        this.users = users;
        this.principal = principal;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "up");
    }

    @PostMapping("/users")
    @ResponseStatus(HttpStatus.CREATED)
    public Account register(@Valid @RequestBody Signup body) {
        return users.register(body, principal.getName());
    }
}
