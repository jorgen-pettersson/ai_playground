package se.jorgen.transcribe.api.service;

import org.springframework.stereotype.Service;
import se.jorgen.transcribe.api.model.ChunkMatch;
import se.jorgen.transcribe.api.repository.ChunkSearchRepository;

import java.util.List;

@Service
public class ChunkSearchService {

    private final ChunkSearchRepository chunkSearchRepository;

    public ChunkSearchService(ChunkSearchRepository chunkSearchRepository) {
        this.chunkSearchRepository = chunkSearchRepository;
    }

    public List<ChunkMatch> searchCourseChunks(String courseId, List<Double> embedding, double minSimilarity, int limit) {
        return chunkSearchRepository.searchCourseChunks(courseId, embedding, minSimilarity, limit);
    }
}
