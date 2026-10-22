# Build context is the REPO ROOT (see infra/docker-compose.yml), because some
# services import sibling modules. Build: docker build -f server/federated-server/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app
WORKDIR /srv/server/federated-server
COPY server/federated-server/requirements.txt ./
RUN HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= NO_PROXY= no_proxy= pip install --no-cache-dir --use-deprecated=legacy-certs --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
COPY hospital-node/ /srv/hospital-node/
COPY server/federated-server/ ./
USER app
EXPOSE 8080
CMD ["python", "server.py", "--address", "0.0.0.0:8080"]
