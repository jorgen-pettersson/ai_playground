package se.jorgen.transcribe.api.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import se.jorgen.transcribe.api.config.RagProperties;

import java.util.List;
import java.util.Map;

@RestController
public class ModelsController {

    private final RagProperties ragProperties;

    public ModelsController(RagProperties ragProperties) {
        this.ragProperties = ragProperties;
    }

    @GetMapping("/v1/models")
    public Map<String, Object> listModels() {
        return Map.of(
                "object", "list",
                "data", List.of(
                        Map.of(
                                "id", ragProperties.getChatModel(),
                                "object", "model",
                                "owned_by", "berget"
                        )
                )
        );
    }
}
