FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TMPDIR=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline ./pipeline
USER 10001:10001
ENTRYPOINT ["python", "-m", "pipeline.run"]
