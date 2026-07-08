package se.jorgen.transcribe.api.controller;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Flux;
import se.jorgen.transcribe.api.model.openai.ChatCompletionRequest;
import se.jorgen.transcribe.api.service.CourseRagService;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/v1/chat/completions")
public class ChatCompletionsController {

    private final CourseRagService courseRagService;
    private final ObjectMapper objectMapper;

    public ChatCompletionsController(CourseRagService courseRagService, ObjectMapper objectMapper) {
        this.courseRagService = courseRagService;
        this.objectMapper = objectMapper;
    }

    @PostMapping
    public ResponseEntity<?> chatCompletions(@Valid @RequestBody ChatCompletionRequest request) {
        final String question;
        final CourseRagService.PreparedContext context;
        try {
            question = courseRagService.extractQuestion(request.getMessages());
            context = courseRagService.prepareContext(question);
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage(), e);
        } catch (RuntimeException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, e.getMessage(), e);
        }

        if (request.isStream()) {
            String completionId = completionId();
            long created = Instant.now().getEpochSecond();
            Flux<String> body = Flux.concat(
                    Flux.just(toSse(chunkPayload(completionId, created, request.getModel(), Map.of("role", "assistant", "content", ""), null))),
                    courseRagService.streamAnswer(context, request.getModel(), request.getTemperature(), request.getMaxTokens())
                            .map(content -> toSse(chunkPayload(completionId, created, request.getModel(), Map.of("content", content), null))),
                    Flux.just(toSse(chunkPayload(completionId, created, request.getModel(), Map.of(), "stop"))),
                    Flux.just("data: [DONE]\n\n")
            );

            return ResponseEntity.ok()
                    .contentType(MediaType.TEXT_EVENT_STREAM)
                    .header(HttpHeaders.CACHE_CONTROL, "no-cache")
                    .header("X-Accel-Buffering", "no")
                    .body(body);
        }

        final String answer;
        try {
            answer = courseRagService.answer(context, request.getModel(), request.getTemperature(), request.getMaxTokens());
        } catch (IllegalArgumentException e) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage(), e);
        } catch (RuntimeException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, e.getMessage(), e);
        }
        Map<String, Object> response = Map.of(
                "id", completionId(),
                "object", "chat.completion",
                "created", Instant.now().getEpochSecond(),
                "model", request.getModel(),
                "choices", List.of(
                        Map.of(
                                "index", 0,
                                "message", Map.of(
                                        "role", "assistant",
                                        "content", answer
                                ),
                                "finish_reason", "stop"
                        )
                ),
                "usage", Map.of(
                        "prompt_tokens", 0,
                        "completion_tokens", 0,
                        "total_tokens", 0
                )
        );
        return ResponseEntity.ok(response);
    }

    private Map<String, Object> chunkPayload(String completionId, long created, String model, Map<String, Object> delta, String finishReason) {
        Map<String, Object> choice = new LinkedHashMap<>();
        choice.put("index", 0);
        choice.put("delta", delta);
        choice.put("finish_reason", finishReason);

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("id", completionId);
        payload.put("object", "chat.completion.chunk");
        payload.put("created", created);
        payload.put("model", model);
        payload.put("choices", List.of(choice));
        return payload;
    }

    private String toSse(Map<String, Object> payload) {
        try {
            return "data: " + objectMapper.writeValueAsString(payload) + "\n\n";
        } catch (JsonProcessingException e) {
            throw new RuntimeException("Failed to serialize SSE payload", e);
        }
    }

    private String completionId() {
        return "chatcmpl-" + UUID.randomUUID().toString().replace("-", "");
    }
}
