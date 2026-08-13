FROM eclipse-temurin:25-jre
WORKDIR /app

COPY target/rag-api-0.0.1-SNAPSHOT.jar /app/rag-api.jar
COPY output/slides/ /app/output/slides/

ENV SERVER_PORT=8101
ENV RAG_SLIDES_DIR=/app/output/slides

EXPOSE 8101

ENTRYPOINT ["java", "-jar", "/app/rag-api.jar"]
