FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Run as an unprivileged user: a compromised process gets no root in the container.
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app

# Exact, pinned versions (requirements.lock), so the image is reproducible.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY src ./src
COPY migrations ./migrations
COPY prompts ./prompts
COPY corpus ./corpus
COPY scripts ./scripts

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=60s --retries=5 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

# bootstrap waits for dependencies, migrates, seeds, then execs uvicorn.
CMD ["python", "scripts/bootstrap.py"]
