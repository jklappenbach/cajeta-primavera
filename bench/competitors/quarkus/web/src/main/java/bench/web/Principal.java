package bench.web;

import jakarta.enterprise.context.RequestScoped;

/** The request's principal, stored by AuthFilter and read by the handler. */
@RequestScoped
public class Principal {
    private String name;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
