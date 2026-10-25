package bench;

import io.micronaut.runtime.http.scope.RequestScope;

/** The request's principal, stored by AuthFilter and read by the handler. */
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
