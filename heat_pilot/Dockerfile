FROM docker.io/library/python:3.13-slim-bookworm
RUN pip install --no-cache-dir aiohttp
COPY heat_pilot /app/heat_pilot
WORKDIR /app
ENV DATA_DIR=/data PYTHONUNBUFFERED=1
CMD ["python", "-m", "heat_pilot.main"]
