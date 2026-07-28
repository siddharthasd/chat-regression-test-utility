FROM acncio.azurecr.io/pythoncio:3.13-bookworm AS builder
USER root:root
WORKDIR /app
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev && \
    rm -rf /var/lib/apt/lists/*
COPY eastus2/002-001-sample-service/src/eval-brew/pyproject.toml .
COPY eastus2/002-001-sample-service/src/eval-brew/src/ src/
RUN pip install --upgrade pip && pip install --no-cache-dir -e .

FROM acncio.azurecr.io/pythoncio:3.13-bookworm AS runtime
WORKDIR /app
USER root
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY eastus2/002-001-sample-service/src/eval-brew/src/ src/
# /docs/{guide} viewer reads markdown files from /app/docs at request time.
COPY eastus2/002-001-sample-service/src/eval-brew/docs/ docs/

EXPOSE 8443
CMD ["uvicorn", "harness.ui:create_app", "--factory", "--host", "0.0.0.0", "--port", "8443"]
