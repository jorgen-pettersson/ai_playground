package se.jknowledge.transcribe.api.repository;

import java.math.BigDecimal;

public interface ChunkMatchProjection {
    Long getId();

    String getPresentationId();

    String getVideoFile();

    Integer getSlideIndex();

    BigDecimal getTimestampStart();

    BigDecimal getTimestampEnd();

    String getImagePath();

    String getSpokenText();

    String getChunkText();

    String getMetadata();

    Double getSimilarity();
}
