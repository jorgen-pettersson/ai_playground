# RAG API

Spring Boot API for forestry-course RAG and slide serving.

## Local Run

Required environment variables:

```bash
export SPRING_DATASOURCE_URL='jdbc:postgresql://localhost:5434/ragtest1'
export SPRING_DATASOURCE_USERNAME='...'
export SPRING_DATASOURCE_PASSWORD='...'
export BERGET_API_KEY='...'
```

Start locally:

```bash
cd api
mvn spring-boot:run
```

Default URL:

- `http://localhost:8101`

Quick checks:

```bash
curl http://localhost:8101/health
curl http://localhost:8101/v1/models
```

## Docker Build

Build from the `transcribe/` directory because the Docker image also includes `output/slides/`.

```bash
cd ..
docker build -f api/Dockerfile -t rag-api:dev .
```

Run the image:

```bash
docker run --rm -p 8101:8101 \
  -e SPRING_DATASOURCE_URL='jdbc:postgresql://host.docker.internal:5434/ragtest1' \
  -e SPRING_DATASOURCE_USERNAME='...' \
  -e SPRING_DATASOURCE_PASSWORD='...' \
  -e BERGET_API_KEY='...' \
  rag-api:dev
```

The image expects slides at:

- `/app/output/slides`

and the app uses:

- `RAG_SLIDES_DIR=/app/output/slides`

## GitHub Actions: Build and Push to Artifact Registry

Workflow file:

- `.github/workflows/build-push-rag-api-gcr.yml`

The workflow builds `api/Dockerfile` and pushes to:

- `europe-north1-docker.pkg.dev/myforesttracker/myforesttracker/rag-api`

### Required GitHub configuration

The workflow uses GitHub OIDC with Workload Identity Federation and the service account:

- `github-actions-aiplaygroud@myforesttracker.iam.gserviceaccount.com`

It expects the workload identity provider:

- `projects/119210083484/locations/global/workloadIdentityPools/github-pool/providers/github-provider`

So no long-lived JSON key secret is required in GitHub for the container push flow.

### Current slide behavior in CI

The repository does not track `output/slides/`, so the workflow currently creates an empty slides directory before the Docker build.

That means:

- the image builds successfully
- slide serving endpoints exist
- slide files will only be available if they are added to the image by a future CI step or another artifact source

## Kubernetes

Kustomize manifests live under:

- `api/k8s/base`
- `api/k8s/overlays/dev`

Default namespace:

- `aiplayground`

Default app port:

- `8101`
