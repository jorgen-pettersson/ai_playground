package se.jknowledge.transcribe.api.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "chunks")
public class ChunkEntity {

    @Id
    private Long id;

    @Column(name = "course_id")
    private String courseId;

    @Column(name = "presentation_id")
    private String presentationId;

    @Column(name = "video_file")
    private String videoFile;

    @Column(name = "slide_index")
    private Integer slideIndex;

    @Column(name = "timestamp_start")
    private Double timestampStart;

    @Column(name = "timestamp_end")
    private Double timestampEnd;

    @Column(name = "image_path")
    private String imagePath;

    @Column(name = "spoken_text")
    private String spokenText;

    @Column(name = "chunk_text")
    private String chunkText;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getCourseId() {
        return courseId;
    }

    public void setCourseId(String courseId) {
        this.courseId = courseId;
    }

    public String getPresentationId() {
        return presentationId;
    }

    public void setPresentationId(String presentationId) {
        this.presentationId = presentationId;
    }

    public String getVideoFile() {
        return videoFile;
    }

    public void setVideoFile(String videoFile) {
        this.videoFile = videoFile;
    }

    public Integer getSlideIndex() {
        return slideIndex;
    }

    public void setSlideIndex(Integer slideIndex) {
        this.slideIndex = slideIndex;
    }

    public Double getTimestampStart() {
        return timestampStart;
    }

    public void setTimestampStart(Double timestampStart) {
        this.timestampStart = timestampStart;
    }

    public Double getTimestampEnd() {
        return timestampEnd;
    }

    public void setTimestampEnd(Double timestampEnd) {
        this.timestampEnd = timestampEnd;
    }

    public String getImagePath() {
        return imagePath;
    }

    public void setImagePath(String imagePath) {
        this.imagePath = imagePath;
    }

    public String getSpokenText() {
        return spokenText;
    }

    public void setSpokenText(String spokenText) {
        this.spokenText = spokenText;
    }

    public String getChunkText() {
        return chunkText;
    }

    public void setChunkText(String chunkText) {
        this.chunkText = chunkText;
    }
}
