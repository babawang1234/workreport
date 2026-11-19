FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY core ./core
COPY webapp ./webapp
COPY assets ./assets

EXPOSE 7860

CMD ["python", "-m", "uvicorn", "webapp.main:app", "--host", "0.0.0.0", "--port", "7860"]
