package bench.web;

import io.quarkus.qute.TemplateData;

@TemplateData
public record Fortune(int id, String message) {
}
