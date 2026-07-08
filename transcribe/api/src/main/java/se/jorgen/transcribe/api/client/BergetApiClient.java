package se.jorgen.transcribe.api.client;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import se.jorgen.transcribe.api.config.RagProperties;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

@Component
public class BergetApiClient {

    private final WebClient webClient;

    public BergetApiClient(WebClient.Builder webClientBuilder, RagProperties ragProperties) {
        String apiKey = ragProperties.getBerget().getApiKey();
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("BERGET_API_KEY is not configured");
        }

        this.webClient = webClientBuilder
                .baseUrl(ragProperties.getBerget().getApiBaseUrl())
                .defaultHeader(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .build();
    }

    public List<Double> embedQuery(String question, String model, int expectedDimensions) {
        Map<String, Object> payload = Map.of(
                "model", model,
                "input", "query: " + question.trim()
        );

        JsonNode result = webClient.post()
                .uri("/embeddings")
                .bodyValue(payload)
                .retrieve()
                .bodyToMono(JsonNode.class)
                .onErrorMap(WebClientResponseException.class, error -> new RuntimeException(error.getResponseBodyAsString(), error))
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
        Map<String, Object> payload = baseChatPayload(model, systemPrompt, userPrompt, temperature, maxTokens);

        JsonNode result = webClient.post()
                .uri("/chat/completions")
                .bodyValue(payload)
                .retrieve()
                .bodyToMono(JsonNode.class)
                .onErrorMap(WebClientResponseException.class, error -> new RuntimeException(error.getResponseBodyAsString(), error))
                .block();

        return result.path("choices").path(0).path("message").path("content").asText("");
    }

    public Flux<String> streamChatComplete(String model, String systemPrompt, String userPrompt, double temperature, int maxTokens) {
        Map<String, Object> payload = new LinkedHashMap<>(baseChatPayload(model, systemPrompt, userPrompt, temperature, maxTokens));
        payload.put("stream", true);

        return webClient.post()
                .uri("/chat/completions")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .bodyValue(payload)
                .retrieve()
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {})
                .onErrorMap(WebClientResponseException.class, error -> new RuntimeException(error.getResponseBodyAsString(), error))
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
            throw new RuntimeException("Failed to parse Berget stream payload: " + payload, e);
        }
    }
}
