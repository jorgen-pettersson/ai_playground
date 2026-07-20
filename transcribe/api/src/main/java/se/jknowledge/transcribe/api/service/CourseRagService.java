package se.jknowledge.transcribe.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import se.jknowledge.transcribe.api.client.BergetApiClient;
import se.jknowledge.transcribe.api.config.RagProperties;
import se.jknowledge.transcribe.api.model.ChunkMatch;
import se.jknowledge.transcribe.api.model.openai.ChatCompletionRequest;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class CourseRagService {

    private static final Logger log = LoggerFactory.getLogger(CourseRagService.class);

    private final BergetApiClient bergetApiClient;
    private final ChunkSearchService chunkSearchService;
    private final PromptBuilder promptBuilder;
    private final RagProperties ragProperties;

    public CourseRagService(BergetApiClient bergetApiClient, ChunkSearchService chunkSearchService, PromptBuilder promptBuilder, RagProperties ragProperties) {
        this.bergetApiClient = bergetApiClient;
        this.chunkSearchService = chunkSearchService;
        this.promptBuilder = promptBuilder;
        this.ragProperties = ragProperties;
    }

    public PreparedContext prepareContext(String question) {
        log.info("Preparing RAG context for questionLength={}", question.length());
        List<Double> embedding = bergetApiClient.embedQuery(
                question,
                ragProperties.getEmbeddingModel(),
                ragProperties.getExpectedEmbeddingDimensions()
        );
        List<ChunkMatch> matches = chunkSearchService.searchCourseChunks(
                ragProperties.getCourseId(),
                embedding,
                ragProperties.getRetrieval().getMinSimilarity(),
                ragProperties.getRetrieval().getLimit()
        );
        log.info("Retrieved {} matching chunks for courseId={}", matches.size(), ragProperties.getCourseId());
        String userPrompt = promptBuilder.buildUserPrompt(question, matches);
        return new PreparedContext(question, matches, userPrompt);
    }

    public String answer(PreparedContext context, String model, double temperature, int maxTokens) {
        return bergetApiClient.chatComplete(model, PromptBuilder.SYSTEM_PROMPT, context.userPrompt(), temperature, maxTokens);
    }

    public Flux<String> streamAnswer(PreparedContext context, String model, double temperature, int maxTokens) {
        return bergetApiClient.streamChatComplete(model, PromptBuilder.SYSTEM_PROMPT, context.userPrompt(), temperature, maxTokens);
    }

    public Flux<String> streamAnswerWithTools(PreparedContext context, ChatCompletionRequest request) {
        log.info("Running streamAnswerWithTools for model={} toolsPresent={}", request.getModel(), request.getTools() != null && !request.getTools().isEmpty());

        List<Map<String, Object>> messages = List.of(
                Map.of("role", "system", "content", PromptBuilder.SYSTEM_PROMPT),
                Map.of("role", "user", "content", context.userPrompt())
        );

        JsonNode raw = bergetApiClient.chatCompleteRaw(
                request.getModel(),
                messages,
                request.getTemperature(),
                request.getMaxTokens(),
                backendTools(),
                request.getToolChoice()
        );

        JsonNode firstChoice = raw.path("choices").path(0);
        JsonNode toolCalls = firstChoice.path("message").path("tool_calls");
        if (!toolCalls.isArray() || toolCalls.isEmpty()) {
            log.info("Berget returned no tool calls in Java streamed path; streaming first answer content as a single chunk");
            String content = firstChoice.path("message").path("content").asText("");
            return content.isBlank() ? Flux.empty() : Flux.just(content);
        }

        log.info("Berget returned {} tool call(s) in Java streamed path", toolCalls.size());

        List<Map<String, Object>> followUpMessages = new ArrayList<>();
        followUpMessages.add(Map.of("role", "system", "content", PromptBuilder.SYSTEM_PROMPT));
        followUpMessages.add(Map.of("role", "user", "content", context.userPrompt()));

        Map<String, Object> assistantMessage = new LinkedHashMap<>();
        assistantMessage.put("role", "assistant");
        assistantMessage.put("content", firstChoice.path("message").path("content").isNull() ? null : firstChoice.path("message").path("content").asText(null));
        assistantMessage.put("tool_calls", toolCalls);
        followUpMessages.add(assistantMessage);

        for (JsonNode toolCall : toolCalls) {
            followUpMessages.add(executeToolCall(toolCall));
        }

        log.info("Sending follow-up Berget streaming request after tool execution");
        return bergetApiClient.streamChatCompleteRaw(
                request.getModel(),
                followUpMessages,
                request.getTemperature(),
                request.getMaxTokens(),
                null,
                null
        );
    }

    public String extractQuestion(List<se.jknowledge.transcribe.api.model.openai.ChatMessageRequest> messages) {
        return promptBuilder.extractQuestion(messages);
    }

    public String answerWithTools(PreparedContext context, ChatCompletionRequest request) {
        log.info("Running answerWithTools for model={} toolsPresent={}", request.getModel(), request.getTools() != null && !request.getTools().isEmpty());
        JsonNode raw = bergetApiClient.chatCompleteRaw(
                request.getModel(),
                List.of(
                        Map.of("role", "system", "content", PromptBuilder.SYSTEM_PROMPT),
                        Map.of("role", "user", "content", context.userPrompt())
                ),
                request.getTemperature(),
                request.getMaxTokens(),
                backendTools(),
                request.getToolChoice()
        );

        JsonNode firstChoice = raw.path("choices").path(0);
        JsonNode toolCalls = firstChoice.path("message").path("tool_calls");
        if (!toolCalls.isArray() || toolCalls.isEmpty()) {
            log.info("Berget returned no tool calls in Java API path");
            return firstChoice.path("message").path("content").asText("");
        }

        log.info("Berget returned {} tool call(s)", toolCalls.size());

        List<Map<String, Object>> followUpMessages = new ArrayList<>();
        followUpMessages.add(Map.of("role", "system", "content", PromptBuilder.SYSTEM_PROMPT));
        followUpMessages.add(Map.of("role", "user", "content", context.userPrompt()));

        Map<String, Object> assistantMessage = new LinkedHashMap<>();
        assistantMessage.put("role", "assistant");
        assistantMessage.put("content", firstChoice.path("message").path("content").isNull() ? null : firstChoice.path("message").path("content").asText(null));
        assistantMessage.put("tool_calls", toolCalls);
        followUpMessages.add(assistantMessage);

        for (JsonNode toolCall : toolCalls) {
            followUpMessages.add(executeToolCall(toolCall));
        }

        log.info("Sending follow-up Berget request after tool execution");

        JsonNode followUp = bergetApiClient.chatCompleteRaw(
                request.getModel(),
                followUpMessages,
                request.getTemperature(),
                request.getMaxTokens(),
                null,
                null
        );
        return followUp.path("choices").path(0).path("message").path("content").asText("");
    }

    public String appendSlideLinks(String answer, List<ChunkMatch> matches, String slideBaseUrl) {
        return promptBuilder.appendSlideLinks(answer, matches, slideBaseUrl);
    }

    private List<Map<String, Object>> backendTools() {
        return List.of(
                Map.of(
                        "type", "function",
                        "function", Map.of(
                                "name", "list_recordings",
                                "description", "Returns the catalog of available recordings and presentations. Use ONLY when the user asks for a list of recordings, presentations, lectures, sessions, or videos. Do NOT use when the user asks about the content, topics, concepts, or knowledge taught in the course.",
                                "parameters", Map.of(
                                        "type", "object",
                                        "properties", Map.of(),
                                        "additionalProperties", false
                                )
                        )
                )
        );
    }

    private Map<String, Object> executeToolCall(JsonNode toolCall) {
        String name = toolCall.path("function").path("name").asText("");
        log.info("Executing tool call in Java API: name={} id={} args={}", name, toolCall.path("id").asText(), toolCall.path("function").path("arguments").asText(""));
        Map<String, Object> payload;
        if ("list_recordings".equals(name)) {
            List<String> recordings = chunkSearchService.listRecordings(ragProperties.getCourseId());
            log.info("list_recordings returned {} rows", recordings.size());
            payload = Map.of("recordings", recordings);
        } else {
            payload = Map.of("error", "Unsupported tool: " + name);
        }

        return Map.of(
                "role", "tool",
                "tool_call_id", toolCall.path("id").asText(),
                "content", serialize(payload)
        );
    }

    private String serialize(Map<String, Object> payload) {
        try {
            return new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsString(payload);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize tool payload", e);
        }
    }

    public record PreparedContext(String question, List<ChunkMatch> matches, String userPrompt) {
    }
}
