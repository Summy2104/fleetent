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
COPY platform.yaml.example .env.example agent.yaml.example agent.env.example ./
COPY alembic.ini ./

# Create runtime dirs
RUN mkdir -p data secrets && chmod +x scripts/docker_entrypoint.sh

EXPOSE 8765

ENTRYPOINT ["./scripts/docker_entrypoint.sh"]
