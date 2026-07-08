package se.jorgen.transcribe.api.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import se.jorgen.transcribe.api.model.ChunkMatch;

import java.util.List;
import java.util.stream.Collectors;

@Repository
public class ChunkSearchRepository {

    private final JdbcTemplate jdbcTemplate;

    public ChunkSearchRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<ChunkMatch> searchCourseChunks(String courseId, List<Double> embedding, double minSimilarity, int limit) {
        String vectorLiteral = "[" + embedding.stream().map(String::valueOf).collect(Collectors.joining(",")) + "]";

        return jdbcTemplate.query(
                """
                select
                    id,
                    presentation_id,
                    video_file,
                    slide_index,
                    timestamp_start,
                    timestamp_end,
                    image_path,
                    spoken_text,
                    chunk_text,
                    cast(metadata as text) as metadata,
                    similarity
                from (
                    select
                        id,
                        presentation_id,
                        video_file,
                        slide_index,
                        timestamp_start,
                        timestamp_end,
                        image_path,
                        spoken_text,
                        chunk_text,
                        metadata,
                        1 - (embedding <=> cast(? as vector)) as similarity
                    from chunks
                    where course_id = ?
                ) matches
                where similarity >= ?
                order by similarity desc, id asc
                limit ?
                """,
                (rs, rowNum) -> new ChunkMatch(
                        rs.getLong("id"),
                        rs.getString("presentation_id"),
                        rs.getString("video_file"),
                        rs.getObject("slide_index", Integer.class),
                        rs.getObject("timestamp_start", Double.class),
                        rs.getObject("timestamp_end", Double.class),
                        rs.getString("image_path"),
                        rs.getString("spoken_text"),
                        rs.getString("chunk_text"),
                        rs.getString("metadata"),
                        rs.getDouble("similarity")
                ),
                vectorLiteral,
                courseId,
                minSimilarity,
                limit
        );
    }
}
