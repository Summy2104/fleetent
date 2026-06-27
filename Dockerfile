FROM docker:27-cli AS docker-cli

FROM python:3.12-slim

WORKDIR /app

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

# Install uv
RUN pip install uv --no-cache-dir

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies first, but defer installing the project until source is copied.
RUN uv sync --no-dev --frozen --no-install-project

# Copy source
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY platform.yaml.example .env.example agent.yaml.example agent.env.example ./
COPY alembic.ini ./

# Create runtime dirs
RUN uv sync --no-dev --frozen && mkdir -p data secrets && chmod +x scripts/docker_entrypoint.sh

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/src:$PYTHONPATH"
ARG GIT_COMMIT=unknown
ENV FLEETENT_BUILD_COMMIT=$GIT_COMMIT
LABEL org.opencontainers.image.revision="$GIT_COMMIT"

EXPOSE 8765

ENTRYPOINT ["./scripts/docker_entrypoint.sh"]
