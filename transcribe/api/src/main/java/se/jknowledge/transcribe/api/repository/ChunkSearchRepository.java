package se.jknowledge.transcribe.api.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import se.jknowledge.transcribe.api.model.ChunkEntity;

import java.util.List;

public interface ChunkSearchRepository extends JpaRepository<ChunkEntity, Long> {

    @Query(value = """
            select
                id as id,
                presentation_id as presentationId,
                video_file as videoFile,
                slide_index as slideIndex,
                timestamp_start as timestampStart,
                timestamp_end as timestampEnd,
                image_path as imagePath,
                spoken_text as spokenText,
                chunk_text as chunkText,
                cast(metadata as text) as metadata,
                similarity as similarity
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
                    1 - (embedding <=> cast(:vectorLiteral as vector)) as similarity
                from chunks
                where course_id = :courseId
            ) matches
            where similarity >= :minSimilarity
            order by similarity desc, id asc
            limit :limit
            """, nativeQuery = true)
    List<ChunkMatchProjection> searchCourseChunks(
            @Param("courseId") String courseId,
            @Param("vectorLiteral") String vectorLiteral,
            @Param("minSimilarity") double minSimilarity,
            @Param("limit") int limit
    );

    @Query(value = """
            select distinct presentation_id
            from chunks
            where course_id = :courseId
              and presentation_id is not null
              and presentation_id <> ''
            order by presentation_id asc
            """, nativeQuery = true)
    List<String> listRecordings(@Param("courseId") String courseId);
}
