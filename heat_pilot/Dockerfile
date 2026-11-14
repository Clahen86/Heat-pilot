FROM docker.io/library/python:3.13-slim-bookworm
RUN pip install --no-cache-dir aiohttp
COPY heat_pilot /app/heat_pilot
COPY integration /app/integration
WORKDIR /app
ARG BUILD_VERSION=dev
ENV DATA_DIR=/data PYTHONUNBUFFERED=1 BUILD_VERSION=${BUILD_VERSION}
CMD ["python", "-m", "heat_pilot.main"]
