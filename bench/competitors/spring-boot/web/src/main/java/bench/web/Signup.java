package bench.web;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record Signup(
        @NotNull(message = "username is required")
        @Size(min = 3, max = 64, message = "username must be 3 to 64 characters") String username,
        @NotNull(message = "password is required")
        @Size(min = 8, message = "password must be at least 8 characters") String password) {
}
