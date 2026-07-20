package se.jknowledge.transcribe.api.controller;

import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.util.UriUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import se.jknowledge.transcribe.api.config.RagProperties;

import java.net.MalformedURLException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@RestController
public class SlidesController {

    private final Path slidesDir;

    public SlidesController(RagProperties ragProperties) {
        this.slidesDir = Path.of(ragProperties.getSlidesDir()).toAbsolutePath().normalize();
    }

    @GetMapping("/slides/{filename}")
    public ResponseEntity<Resource> getSlide(@PathVariable String filename) {
        String decoded = UriUtils.decode(filename, StandardCharsets.UTF_8);
        Path filePath = slidesDir.resolve(decoded).normalize();
        if (!filePath.startsWith(slidesDir)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid slide path");
        }
        if (!Files.isRegularFile(filePath)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Slide not found");
        }

        try {
            Resource resource = new UrlResource(filePath.toUri());
            return ResponseEntity.ok()
                    .contentType(MediaType.IMAGE_JPEG)
                    .body(resource);
        } catch (MalformedURLException e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Failed to serve slide", e);
        }
    }
}
