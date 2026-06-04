FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install uv --no-cache-dir

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps)
RUN uv sync --no-dev --frozen

# Copy source
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
COPY config/agent.yaml.example ./config/
COPY .env.example ./
COPY alembic.ini ./

# Create data and config dirs
RUN mkdir -p data config secrets && chmod +x scripts/docker_entrypoint.sh

EXPOSE 8765

ENTRYPOINT ["./scripts/docker_entrypoint.sh"]
