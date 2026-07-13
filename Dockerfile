FROM python:3.13-slim AS builder
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --upgrade pip && pip install --no-cache-dir -e .

FROM python:3.13-slim AS runtime
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ src/
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh && useradd -m -u 1001 harness
USER harness
EXPOSE 8000
CMD ["./docker-entrypoint.sh"]
