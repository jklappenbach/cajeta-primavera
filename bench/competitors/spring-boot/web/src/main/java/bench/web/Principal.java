package bench.web;

import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

/** The request's principal, stored by AuthFilter and read by the handler. */
@Component
@RequestScope
public class Principal {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
