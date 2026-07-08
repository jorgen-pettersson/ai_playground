package se.jorgen.transcribe.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;
import se.jorgen.transcribe.api.model.ChunkMatch;
import se.jorgen.transcribe.api.model.openai.ChatMessageRequest;

import java.util.ArrayList;
import java.util.List;

@Component
public class PromptBuilder {

    public static final String SYSTEM_PROMPT = "You are an assistant for a forestry course. Answer using the provided course material whenever possible. "
            + "If the course material does not contain enough information, clearly say so instead of making up an answer. "
            + "When possible, cite the presentation name and slide number."
            + "If the question are in swedish, answer in swedish. If the question is in english, answer in english.";

    public String extractQuestion(List<ChatMessageRequest> messages) {
        for (int i = messages.size() - 1; i >= 0; i--) {
            ChatMessageRequest message = messages.get(i);
            String text = messageText(message);
            if ("user".equals(message.getRole()) && !text.isBlank()) {
                return text;
            }
        }
        throw new IllegalArgumentException("Request must include at least one non-empty user message");
    }

    public String buildUserPrompt(String question, List<ChunkMatch> matches) {
        List<String> sections = new ArrayList<>();
        if (matches.isEmpty()) {
            sections.add("No matching course material found.");
        } else {
            for (ChunkMatch match : matches) {
                sections.add(formatContextBlock(match));
            }
        }

        return "Question:\n\n" + question.strip() + "\n\nCourse material:\n\n" + String.join("\n\n-------------------\n\n", sections);
    }

    private String formatContextBlock(ChunkMatch match) {
        StringBuilder builder = new StringBuilder();
        String presentationName = firstNonBlank(match.presentationId(), match.videoFile(), "Unknown presentation");
        builder.append("Presentation:\n").append(presentationName).append("\n\n");

        if (match.slideIndex() != null) {
            builder.append("Slide ").append(match.slideIndex()).append("\n\n");
        }

        String start = formatTimestamp(match.timestampStart());
        String end = formatTimestamp(match.timestampEnd());
        if (start != null && end != null) {
            builder.append("Timestamp:\n").append(start).append(" - ").append(end).append("\n\n");
        } else if (start != null) {
            builder.append("Timestamp:\n").append(start).append("\n\n");
        }

        String transcript = firstNonBlank(match.chunkText(), match.spokenText(), "");
        builder.append("Transcript:\n").append(transcript.strip());
        return builder.toString();
    }

    private String formatTimestamp(Double seconds) {
        if (seconds == null) {
            return null;
        }
        int totalSeconds = seconds.intValue();
        int hours = totalSeconds / 3600;
        int minutes = (totalSeconds % 3600) / 60;
        int remainingSeconds = totalSeconds % 60;
        return "%02d:%02d:%02d".formatted(hours, minutes, remainingSeconds);
    }

    private String messageText(ChatMessageRequest message) {
        JsonNode content = message.getContent();
        if (content == null || content.isNull()) {
            return "";
        }
        if (content.isTextual()) {
            return content.asText("").strip();
        }
        if (content.isArray()) {
            List<String> parts = new ArrayList<>();
            for (JsonNode item : content) {
                if (item.isObject() && "text".equals(item.path("type").asText())) {
                    String text = item.path("text").asText("").strip();
                    if (!text.isBlank()) {
                        parts.add(text);
                    }
                }
            }
            return String.join("\n", parts).strip();
        }
        return "";
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return "";
    }
}
