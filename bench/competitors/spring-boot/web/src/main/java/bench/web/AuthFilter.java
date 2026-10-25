package bench.web;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Guards /users: admits only `Bearer bench-7f3c9a1e` and stores the principal. */
@Component
public class AuthFilter extends OncePerRequestFilter {
    private static final byte[] UNAUTHORIZED = "{\"error\":\"unauthorized\"}".getBytes(StandardCharsets.UTF_8);
    private final Principal principal;

    public AuthFilter(Principal principal) {
        this.principal = principal;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !"/users".equals(request.getRequestURI());
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        if (!"Bearer bench-7f3c9a1e".equals(request.getHeader("Authorization"))) {
            response.setStatus(401);
            response.setContentType("application/json");
            response.setContentLength(UNAUTHORIZED.length);
            response.getOutputStream().write(UNAUTHORIZED);
            return;
        }
        principal.setName("bench-client");
        chain.doFilter(request, response);
    }
}
