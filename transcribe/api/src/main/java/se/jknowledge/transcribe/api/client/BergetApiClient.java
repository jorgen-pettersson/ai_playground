package se.jknowledge.transcribe.api.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import se.jknowledge.transcribe.api.config.RagProperties;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Component
public class BergetApiClient {

    private static final Logger log = LoggerFactory.getLogger(BergetApiClient.class);

    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    public BergetApiClient(WebClient.Builder webClientBuilder, RagProperties ragProperties, ObjectMapper objectMapper) {
        String apiKey = ragProperties.getBerget().getApiKey();
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("BERGET_API_KEY is not configured");
        }

        this.objectMapper = objectMapper;

        this.webClient = webClientBuilder
                .baseUrl(ragProperties.getBerget().getApiBaseUrl())
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    public List<Double> embedQuery(String question, String model, int expectedDimensions) {
        log.info("Requesting Berget embedding: model={} expectedDimensions={} questionLength={}", model, expectedDimensions, question.length());
        Map<String, Object> payload = Map.of(
                "model", model,
                "input", "query: " + question.trim()
        );

        JsonNode result = webClient.post()
                .uri("/embeddings")
                .bodyValue(payload)
                .retrieve()
                .bodyToMono(JsonNode.class)
                .onErrorMap(WebClientResponseException.class, error -> {
                    log.error("Berget embeddings request failed: status={} body={}", error.getStatusCode(), error.getResponseBodyAsString(), error);
                    return new RuntimeException(error.getResponseBodyAsString(), error);
                })
                .block();

        JsonNode embeddingNode = result.path("data").path(0).path("embedding");
        List<Double> embedding = new ArrayList<>();
        embeddingNode.forEach(node -> embedding.add(node.asDouble()));

        if (embedding.size() != expectedDimensions) {
            throw new IllegalStateException(
                    "Model %s returned %s dimensions, expected %s".formatted(model, embedding.size(), expectedDimensions)
            );
        }

        return embedding;
    }

    public String chatComplete(String model, String systemPrompt, String userPrompt, double temperature, int maxTokens) {
        log.info("Requesting Berget chat completion: model={} temperature={} maxTokens={} userPromptLength={}", model, temperature, maxTokens, userPrompt.length());
        Map<String, Object> payload = baseChatPayload(model, systemPrompt, userPrompt, temperature, maxTokens);

        JsonNode result = webClient.post()
                .uri("/chat/completions")
                .bodyValue(payload)
                .retrieve()
                .bodyToMono(JsonNode.class)
                .onErrorMap(WebClientResponseException.class, error -> {
                    log.error("Berget chat completion failed: status={} body={}", error.getStatusCode(), error.getResponseBodyAsString(), error);
                    return new RuntimeException(error.getResponseBodyAsString(), error);
                })
                .block();

        return result.path("choices").path(0).path("message").path("content").asText("");
    }

    public JsonNode chatCompleteRaw(
            String model,
            List<Map<String, Object>> messages,
            double temperature,
            int maxTokens,
            List<Map<String, Object>> tools,
            JsonNode toolChoice
    ) {
        log.info("Requesting raw Berget chat completion: model={} temperature={} maxTokens={} toolsCount={} messagesCount={}",
                model, temperature, maxTokens, tools == null ? 0 : tools.size(), messages.size());
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("model", model);
        payload.put("messages", messages);
        payload.put("temperature", temperature);
        payload.put("max_tokens", maxTokens);
        if (tools != null && !tools.isEmpty()) {
            payload.put("tools", tools);
        }
        if (toolChoice != null && !toolChoice.isNull()) {
            payload.put("tool_choice", objectMapper.convertValue(toolChoice, Object.class));
        }

        return webClient.post()
                .uri("/chat/completions")
                .bodyValue(payload)
                .retrieve()
                .bodyToMono(JsonNode.class)
                .onErrorMap(WebClientResponseException.class, error -> {
                    log.error("Berget raw chat completion failed: status={} body={}", error.getStatusCode(), error.getResponseBodyAsString(), error);
                    return new RuntimeException(error.getResponseBodyAsString(), error);
                })
                .block();
    }

    public Flux<String> streamChatComplete(String model, String systemPrompt, String userPrompt, double temperature, int maxTokens) {
        log.info("Requesting Berget streaming chat completion: model={} temperature={} maxTokens={} userPromptLength={}", model, temperature, maxTokens, userPrompt.length());
        Map<String, Object> payload = new LinkedHashMap<>(baseChatPayload(model, systemPrompt, userPrompt, temperature, maxTokens));
        payload.put("stream", true);

        return streamChatCompletePayload(payload);
    }

    public Flux<String> streamChatCompleteRaw(
            String model,
            List<Map<String, Object>> messages,
            double temperature,
            int maxTokens,
            List<Map<String, Object>> tools,
            JsonNode toolChoice
    ) {
        log.info("Requesting raw Berget streaming chat completion: model={} temperature={} maxTokens={} toolsCount={} messagesCount={}",
                model, temperature, maxTokens, tools == null ? 0 : tools.size(), messages.size());

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("model", model);
        payload.put("messages", messages);
        payload.put("temperature", temperature);
        payload.put("max_tokens", maxTokens);
        payload.put("stream", true);
        if (tools != null && !tools.isEmpty()) {
            payload.put("tools", tools);
        }
        if (toolChoice != null && !toolChoice.isNull()) {
            payload.put("tool_choice", objectMapper.convertValue(toolChoice, Object.class));
        }

        return streamChatCompletePayload(payload);
    }

    private Flux<String> streamChatCompletePayload(Map<String, Object> payload) {

        return webClient.post()
                .uri("/chat/completions")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .bodyValue(payload)
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {})
                .onErrorMap(WebClientResponseException.class, error -> {
                    log.error("Berget streaming chat completion failed: status={} body={}", error.getStatusCode(), error.getResponseBodyAsString(), error);
                    return new RuntimeException(error.getResponseBodyAsString(), error);
                })
                .map(ServerSentEvent::data)
                .filter(Objects::nonNull)
                .filter(data -> !data.isBlank())
                .filter(data -> !"[DONE]".equals(data))
                .flatMapIterable(this::extractStreamContent);
    }

    private Map<String, Object> baseChatPayload(String model, String systemPrompt, String userPrompt, double temperature, int maxTokens) {
        return Map.of(
                "model", model,
                "messages", List.of(
                        Map.of("role", "system", "content", systemPrompt),
                        Map.of("role", "user", "content", userPrompt)
                ),
                "temperature", temperature,
                "max_tokens", maxTokens
        );
    }

    private List<String> extractStreamContent(String payload) {
        try {
            JsonNode root = new com.fasterxml.jackson.databind.ObjectMapper().readTree(payload);
            JsonNode choice = root.path("choices").path(0);
            JsonNode delta = choice.path("delta");
            JsonNode content = delta.path("content");

            if (content.isTextual()) {
                return List.of(content.asText());
            }
            if (content.isArray()) {
                List<String> parts = new ArrayList<>();
                for (JsonNode item : content) {
                    if (item.isTextual()) {
                        parts.add(item.asText());
                    } else if (item.isObject()) {
                        String text = item.path("text").asText("");
                        if (!text.isBlank()) {
                            parts.add(text);
                        }
                    }
                }
                return parts;
            }

            JsonNode messageContent = choice.path("message").path("content");
            if (messageContent.isTextual()) {
                return List.of(messageContent.asText());
            }
            return List.of();
        } catch (Exception e) {
            log.error("Failed to parse Berget stream payload: {}", payload, e);
            throw new RuntimeException("Failed to parse Berget stream payload: " + payload, e);
        }
    }
}
