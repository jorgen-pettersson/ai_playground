package se.jknowledge.transcribe.api.controller;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Flux;
import se.jknowledge.transcribe.api.model.openai.ChatCompletionRequest;
import se.jknowledge.transcribe.api.service.CourseRagService;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/v1/chat/completions")
public class ChatCompletionsController {

    private static final Logger log = LoggerFactory.getLogger(ChatCompletionsController.class);

    private final CourseRagService courseRagService;
    private final ObjectMapper objectMapper;

    public ChatCompletionsController(CourseRagService courseRagService, ObjectMapper objectMapper) {
        this.courseRagService = courseRagService;
        this.objectMapper = objectMapper;
    }

    @PostMapping
    public ResponseEntity<?> chatCompletions(@Valid @RequestBody ChatCompletionRequest request, jakarta.servlet.http.HttpServletRequest httpRequest) {
        final String question;
        final CourseRagService.PreparedContext context;
        try {
            question = courseRagService.extractQuestion(request.getMessages());
            log.info("/v1/chat/completions request received: model={} stream={} toolsPresent={} questionPreview={}",
                    request.getModel(),
                    request.isStream(),
                    request.getTools() != null && !request.getTools().isEmpty(),
                    question.length() > 120 ? question.substring(0, 117) + "..." : question);
            context = courseRagService.prepareContext(question);
        } catch (IllegalArgumentException e) {
            log.warn("Bad chat completion request: {}", e.getMessage(), e);
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage(), e);
        } catch (RuntimeException e) {
            log.error("Failed during question extraction or RAG preparation", e);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, e.getMessage(), e);
        }

        String slideBaseUrl = baseUrl(httpRequest) + "/slides/";

        if (request.isStream()) {
            String completionId = completionId();
            long created = Instant.now().getEpochSecond();
            Flux<String> answerStream;
            if (request.getTools() != null && !request.getTools().isEmpty()) {
                log.info("Handling stream request with tool support enabled");
                answerStream = courseRagService.streamAnswerWithTools(context, request);
            } else {
                log.info("Handling stream request with plain RAG answer path");
                answerStream = courseRagService.streamAnswer(context, request.getModel(), request.getTemperature(), request.getMaxTokens());
            }
            String slideLinks = courseRagService.appendSlideLinks("", context.matches(), slideBaseUrl).strip();
            Flux<String> body = Flux.concat(
                    Flux.just(toSse(chunkPayload(completionId, created, request.getModel(), Map.of("role", "assistant", "content", ""), null))),
                    answerStream
                            .map(content -> toSse(chunkPayload(completionId, created, request.getModel(), Map.of("content", content), null))),
                    slideLinks.isBlank()
                            ? Flux.empty()
                            : Flux.just(toSse(chunkPayload(completionId, created, request.getModel(), Map.of("content", slideLinks), null))),
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
            if (request.getTools() != null && !request.getTools().isEmpty()) {
                log.info("Handling non-stream request with tool support enabled");
                answer = courseRagService.answerWithTools(context, request);
            } else {
                log.info("Handling non-stream request with plain RAG answer path");
                answer = courseRagService.answer(context, request.getModel(), request.getTemperature(), request.getMaxTokens());
            }
        } catch (IllegalArgumentException e) {
            log.warn("Bad chat completion request during answer generation: {}", e.getMessage(), e);
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage(), e);
        } catch (RuntimeException e) {
            log.error("Failed during answer generation", e);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, e.getMessage(), e);
        }
        String answerWithSlides = courseRagService.appendSlideLinks(answer, context.matches(), slideBaseUrl);
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
                                        "content", answerWithSlides
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

    private String baseUrl(jakarta.servlet.http.HttpServletRequest request) {
        StringBuilder builder = new StringBuilder();
        builder.append(request.getScheme()).append("://").append(request.getServerName());
        int port = request.getServerPort();
        boolean defaultPort = ("http".equalsIgnoreCase(request.getScheme()) && port == 80)
                || ("https".equalsIgnoreCase(request.getScheme()) && port == 443);
        if (!defaultPort) {
            builder.append(":").append(port);
        }
        return builder.toString();
    }
}
