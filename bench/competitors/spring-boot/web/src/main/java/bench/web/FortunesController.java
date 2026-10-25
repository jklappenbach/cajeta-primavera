package bench.web;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class FortunesController {
    private final FortuneRepository repository;

    public FortunesController(FortuneRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/fortunes")
    public String fortunes(Model model) {
        List<Fortune> rows = new ArrayList<>(repository.findAll());
        rows.sort(Comparator.comparing(Fortune::message));
        model.addAttribute("fortunes", rows);
        return "fortunes";
    }
}
