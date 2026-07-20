package se.jknowledge.transcribe.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "rag")
public class RagProperties {

    private final Berget berget = new Berget();
    private final Retrieval retrieval = new Retrieval();
    private String courseId = "skogskurs";
    private String embeddingModel = "intfloat/multilingual-e5-large-instruct";
    private int expectedEmbeddingDimensions = 1024;
    private String chatModel = "openai/gpt-oss-120b";
    private String slidesDir = "../output/slides";

    public Berget getBerget() {
        return berget;
    }

    public Retrieval getRetrieval() {
        return retrieval;
    }

    public String getCourseId() {
        return courseId;
    }

    public void setCourseId(String courseId) {
        this.courseId = courseId;
    }

    public String getEmbeddingModel() {
        return embeddingModel;
    }

    public void setEmbeddingModel(String embeddingModel) {
        this.embeddingModel = embeddingModel;
    }

    public int getExpectedEmbeddingDimensions() {
        return expectedEmbeddingDimensions;
    }

    public void setExpectedEmbeddingDimensions(int expectedEmbeddingDimensions) {
        this.expectedEmbeddingDimensions = expectedEmbeddingDimensions;
    }

    public String getChatModel() {
        return chatModel;
    }

    public void setChatModel(String chatModel) {
        this.chatModel = chatModel;
    }

    public String getSlidesDir() {
        return slidesDir;
    }

    public void setSlidesDir(String slidesDir) {
        this.slidesDir = slidesDir;
    }

    public static class Berget {
        private String apiBaseUrl = "https://api.berget.ai/v1";
        private String apiKey = "";

        public String getApiBaseUrl() {
            return apiBaseUrl;
        }

        public void setApiBaseUrl(String apiBaseUrl) {
            this.apiBaseUrl = apiBaseUrl;
        }

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey;
        }
    }

    public static class Retrieval {
        private double minSimilarity = 0.7;
        private int limit = 5;

        public double getMinSimilarity() {
            return minSimilarity;
        }

        public void setMinSimilarity(double minSimilarity) {
            this.minSimilarity = minSimilarity;
        }

        public int getLimit() {
            return limit;
        }

        public void setLimit(int limit) {
            this.limit = limit;
        }
    }
}
