# Build context is the REPO ROOT (see infra/docker-compose.yml), because some
# services import sibling modules. Build: docker build -f server/validation/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app
WORKDIR /srv/server/validation
COPY server/validation/requirements.txt ./
RUN HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= NO_PROXY= no_proxy= pip install --no-cache-dir --use-deprecated=legacy-certs --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
COPY server/validation/ ./
USER app
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
