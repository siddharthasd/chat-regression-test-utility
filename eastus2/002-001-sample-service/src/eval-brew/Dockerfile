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

# entrypoint.sh serves HTTPS on 8443. It uses a cert mounted at /app/ssl/ when
# available (e.g. a K8s TLS secret), or generates a self-signed cert at startup
# as a fallback. Either way the private key never appears in an image layer,
# which avoids the Aqua "sensitive data found in image" compliance failure.
COPY eastus2/002-001-sample-service/src/eval-brew/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8443
CMD ["/app/entrypoint.sh"]
