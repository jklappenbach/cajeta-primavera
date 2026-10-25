package bench.web;

import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** The first failing rule, in the contract's order, as {"error": message}. */
@RestControllerAdvice
public class ValidationAdvice {
    private static final List<String> ORDER = List.of(
            "username is required", "password is required",
            "username must be 3 to 64 characters", "password must be at least 8 characters");

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Map<String, String> invalid(MethodArgumentNotValidException e) {
        String first = null;
        int best = Integer.MAX_VALUE;
        for (FieldError fe : e.getBindingResult().getFieldErrors()) {
            int i = ORDER.indexOf(fe.getDefaultMessage());
            if (i >= 0 && i < best) {
                best = i;
                first = fe.getDefaultMessage();
            }
        }
        return Map.of("error", first == null ? "invalid request" : first);
    }
}
