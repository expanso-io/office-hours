FROM ghcr.io/astral-sh/uv@sha256:020e9eefae64e99ea2da39bcd1af1294be0a0b01e98ebad4dbedfd8b729500f7
WORKDIR /app
ENV UV_NO_DEV=1 UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY server ./server
COPY web ./web
COPY pipelines ./pipelines
CMD ["uv", "run", "--no-sync", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
