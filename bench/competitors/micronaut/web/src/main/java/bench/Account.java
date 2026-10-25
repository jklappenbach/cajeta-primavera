package bench;

import io.micronaut.serde.annotation.Serdeable;

@Serdeable
public record Account(String id, String username, boolean confirmed, String registeredBy) {
}
