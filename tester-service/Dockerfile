FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY cra-service/requirements.txt cra-service/requirements-harness.txt ./cra-service/
RUN pip install --no-cache-dir -r cra-service/requirements-harness.txt
COPY cra-service/test_api.py cra-service/conftest.py cra-service/http_evidence.py ./cra-service/
COPY cra-service/autograder/ ./cra-service/autograder/
COPY docs/openapi.yaml ./docs/openapi.yaml
COPY fixtures/ ./fixtures/
COPY tester-service/app.py ./tester-service/app.py
ARG BUILD_SHA=unknown
ENV BUILD_SHA=$BUILD_SHA
WORKDIR /app/tester-service
CMD ["sh", "-c", "exec uvicorn app:app --host 0.0.0.0 --port \"${PORT:-8080}\" --timeout-graceful-shutdown 5"]
