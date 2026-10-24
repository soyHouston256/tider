FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ src/
RUN pip install --no-cache-dir uv==0.11.16 && uv sync --frozen --no-dev --extra gcp
RUN useradd -r tiderops
USER tiderops
ENV LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
EXPOSE 8080
CMD ["/app/.venv/bin/python", "-m", "tider.console", "--host", "0.0.0.0", "--port", "8080"]
