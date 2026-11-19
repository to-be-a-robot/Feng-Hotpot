# The API as a container, for hosts other than Render (Railway, Fly.io, ...).
#   docker build -t feng-api . && docker run -p 8000:8000 --env-file .env feng-api
FROM python:3.12-slim
WORKDIR /app
COPY workers/pyproject.toml workers/pyproject.toml
COPY workers/feng_workers workers/feng_workers
RUN pip install --no-cache-dir -e ./workers
COPY config config
COPY prompts prompts
COPY supabase supabase
COPY seed seed
WORKDIR /app/workers
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "python -m feng_workers.migrate && uvicorn feng_workers.api:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
