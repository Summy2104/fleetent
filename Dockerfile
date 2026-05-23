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
COPY alembic.ini ./

# Create data and config dirs
RUN mkdir -p data config

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "mini_agent.server:app", "--host", "0.0.0.0", "--port", "8000"]
