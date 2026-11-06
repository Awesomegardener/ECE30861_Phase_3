FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY cra-service/requirements.txt cra-service/requirements-harness.txt ./cra-service/
RUN pip install --no-cache-dir -r cra-service/requirements-harness.txt
COPY cra-service/main.py cra-service/sbom_validation.py cra-service/conftest.py cra-service/test_api.py cra-service/http_evidence.py ./cra-service/
COPY cra-service/phase4.py cra-service/timestamps.py cra-service/test_phase4_api.py ./cra-service/
COPY cra-service/osv_source.py cra-service/purl_matching.py ./cra-service/
COPY cra-service/vendor/osv/ ./cra-service/vendor/osv/
COPY scripts/osv_snapshot.py ./scripts/osv_snapshot.py
COPY cra-service/autograder/ ./cra-service/autograder/
COPY docs/openapi.yaml ./docs/openapi.yaml
COPY fixtures/ ./fixtures/
ARG BUILD_SHA=unknown
ENV BUILD_SHA=$BUILD_SHA
WORKDIR /app/cra-service
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --timeout-graceful-shutdown 5"]

# Coverage dependency is selected explicitly, never in the default runtime.
FROM runtime AS coverage-runtime
COPY cra-service/requirements-coverage.txt ./requirements-coverage.txt
RUN pip install --no-cache-dir -r requirements-coverage.txt

# Explicit deployment image for the resettable, single-replica grading service.
FROM coverage-runtime AS grading
COPY docs/coverage-model.json /app/docs/coverage-model.json
CMD ["python", "-m", "autograder.grading_server"]

# Default Cloud Build/Compose image retains the existing runtime and entrypoint.
FROM runtime AS production
