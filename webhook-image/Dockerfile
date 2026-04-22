FROM python:3.11-slim

# nomad CLI needed to inspect + run jobs
RUN apt-get update && apt-get install -y curl unzip && \
    curl -fsSL https://releases.hashicorp.com/nomad/1.9.7/nomad_1.9.7_linux_amd64.zip -o /tmp/nomad.zip && \
    unzip /tmp/nomad.zip -d /usr/local/bin && \
    rm /tmp/nomad.zip && \
    apt-get remove -y unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY webhook.py /app/webhook.py

EXPOSE 9000
CMD ["python3", "/app/webhook.py"]
