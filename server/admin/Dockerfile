# Build context is the REPO ROOT (see docker-compose.yml), because some
# services import sibling modules. Build: docker build -f module7-admin/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app
WORKDIR /srv/module7-admin
COPY module7-admin/requirements.txt ./
RUN HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= NO_PROXY= no_proxy= pip install --no-cache-dir --use-deprecated=legacy-certs --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
COPY module3-fedlearning/ /srv/module3-fedlearning/
COPY module7-admin/ ./
USER app
EXPOSE 8005
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
