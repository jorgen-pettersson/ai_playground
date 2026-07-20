package se.jknowledge.transcribe.api.model;

public record ChunkMatch(
        long id,
        String presentationId,
        String videoFile,
        Integer slideIndex,
        Double timestampStart,
        Double timestampEnd,
        String imagePath,
        String spokenText,
        String chunkText,
        String metadata,
        double similarity
) {
}
