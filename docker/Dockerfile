# Heat Pilot outside Home Assistant OS (Docker): set HA_URL and HA_TOKEN (a long-lived access token).
FROM docker.io/library/python:3.13-slim-bookworm
RUN pip install --no-cache-dir aiohttp
COPY heat_pilot/heat_pilot /app/heat_pilot
WORKDIR /app
ENV DATA_DIR=/data PYTHONUNBUFFERED=1 PORT=8099
VOLUME /data
EXPOSE 8099
CMD ["python", "-m", "heat_pilot.main"]
