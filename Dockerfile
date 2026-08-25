FROM python:3.12-alpine
LABEL org.opencontainers.image.title="Emby Dynamic Collections Manager" \
      org.opencontainers.image.description="Dynamic Emby 4.10 collection synchronization"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && mkdir -p /config
COPY src/ .
VOLUME ["/config"]
CMD ["python", "app.py"]
