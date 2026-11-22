FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/g3ap
USER 65534:65534
ENTRYPOINT ["python3", "-u", "/opt/g3ap/server.py"]
