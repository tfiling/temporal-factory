FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git gh nodejs npm ca-certificates bash \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

# Claude Code refuses bypassPermissions as root.
RUN useradd -m -u 1000 factory && mkdir /app /data && chown factory /app /data
WORKDIR /app

COPY pyproject.toml checks.sh entrypoint.sh ./
COPY factory ./factory
COPY tests ./tests
RUN pip install --no-cache-dir -e ".[dev]"

USER factory
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "factory.worker"]
