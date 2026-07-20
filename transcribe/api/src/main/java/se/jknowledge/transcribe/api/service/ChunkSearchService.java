package se.jknowledge.transcribe.api.service;

import org.springframework.stereotype.Service;
import se.jknowledge.transcribe.api.model.ChunkMatch;
import se.jknowledge.transcribe.api.repository.ChunkMatchProjection;
import se.jknowledge.transcribe.api.repository.ChunkSearchRepository;

import java.math.BigDecimal;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class ChunkSearchService {

    private final ChunkSearchRepository chunkSearchRepository;

    public ChunkSearchService(ChunkSearchRepository chunkSearchRepository) {
        this.chunkSearchRepository = chunkSearchRepository;
    }

    public List<ChunkMatch> searchCourseChunks(String courseId, List<Double> embedding, double minSimilarity, int limit) {
        String vectorLiteral = "[" + embedding.stream().map(String::valueOf).collect(Collectors.joining(",")) + "]";
        return chunkSearchRepository.searchCourseChunks(courseId, vectorLiteral, minSimilarity, limit)
                .stream()
                .map(this::toChunkMatch)
                .toList();
    }

    public List<String> listRecordings(String courseId) {
        return chunkSearchRepository.listRecordings(courseId);
    }

    private ChunkMatch toChunkMatch(ChunkMatchProjection projection) {
        return new ChunkMatch(
                projection.getId(),
                projection.getPresentationId(),
                projection.getVideoFile(),
                projection.getSlideIndex(),
                toDouble(projection.getTimestampStart()),
                toDouble(projection.getTimestampEnd()),
                projection.getImagePath(),
                projection.getSpokenText(),
                projection.getChunkText(),
                projection.getMetadata(),
                projection.getSimilarity() == null ? 0.0 : projection.getSimilarity()
        );
    }

    private Double toDouble(BigDecimal value) {
        return value == null ? null : value.doubleValue();
    }
}
