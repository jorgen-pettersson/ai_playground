package se.jorgen.transcribe.api.service;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import se.jorgen.transcribe.api.client.BergetApiClient;
import se.jorgen.transcribe.api.config.RagProperties;
import se.jorgen.transcribe.api.model.ChunkMatch;

import java.util.List;

@Service
public class CourseRagService {

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
        String userPrompt = promptBuilder.buildUserPrompt(question, matches);
        return new PreparedContext(question, matches, userPrompt);
    }

    public String answer(PreparedContext context, String model, double temperature, int maxTokens) {
        return bergetApiClient.chatComplete(model, PromptBuilder.SYSTEM_PROMPT, context.userPrompt(), temperature, maxTokens);
    }

    public Flux<String> streamAnswer(PreparedContext context, String model, double temperature, int maxTokens) {
        return bergetApiClient.streamChatComplete(model, PromptBuilder.SYSTEM_PROMPT, context.userPrompt(), temperature, maxTokens);
    }

    public String extractQuestion(List<se.jorgen.transcribe.api.model.openai.ChatMessageRequest> messages) {
        return promptBuilder.extractQuestion(messages);
    }

    public record PreparedContext(String question, List<ChunkMatch> matches, String userPrompt) {
    }
}
