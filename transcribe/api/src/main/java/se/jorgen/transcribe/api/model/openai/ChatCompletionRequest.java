package se.jorgen.transcribe.api.model.openai;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import jakarta.validation.constraints.NotEmpty;

import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class ChatCompletionRequest {

    private String model = "openai/gpt-oss-120b";
    @NotEmpty
    private List<ChatMessageRequest> messages;
    private double temperature = 0.7;
    @JsonAlias({"max_tokens", "max_completion_tokens"})
    private int maxTokens = 1000;
    private boolean stream = false;

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public List<ChatMessageRequest> getMessages() {
        return messages;
    }

    public void setMessages(List<ChatMessageRequest> messages) {
        this.messages = messages;
    }

    public double getTemperature() {
        return temperature;
    }

    public void setTemperature(double temperature) {
        this.temperature = temperature;
    }

    public int getMaxTokens() {
        return maxTokens;
    }

    public void setMaxTokens(int maxTokens) {
        this.maxTokens = maxTokens;
    }

    public boolean isStream() {
        return stream;
    }

    public void setStream(boolean stream) {
        this.stream = stream;
    }
}
