package se.jknowledge.transcribe.api.controller;

import jakarta.persistence.PersistenceException;
import org.hibernate.exception.JDBCConnectionException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class DatabaseExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(DatabaseExceptionHandler.class);

    @ExceptionHandler({
            CannotGetJdbcConnectionException.class,
            CannotCreateTransactionException.class,
            JDBCConnectionException.class,
            DataAccessException.class,
            PersistenceException.class
    })
    public ResponseEntity<Map<String, Object>> handleDatabaseUnavailable(Exception e) {
        log.warn("Database unavailable: {}", e.getMessage());
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "status", "unavailable",
                        "error", "Database unavailable"
                ));
    }
}
