FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV OR_EXTRACTOR_OUTPUT_DIR=/tmp/or-extractor

WORKDIR /app

COPY pyproject.toml README.md ./
COPY or_extractor ./or_extractor
COPY assets ./assets

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8080

CMD ["uvicorn", "or_extractor.web_app:app", "--host", "0.0.0.0", "--port", "8080"]
