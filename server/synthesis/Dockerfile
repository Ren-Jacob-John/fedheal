
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Install the system library required by LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app

WORKDIR /srv/server/synthesis

COPY server/synthesis/requirements.txt ./
RUN HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= NO_PROXY= no_proxy= pip install --no-cache-dir --use-deprecated=legacy-certs --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

COPY server/model-zoo/ /srv/server/model-zoo/
COPY server/condition-router/ /srv/server/condition-router/
COPY module3-fedlearning/uci_heart.py /srv/module3-fedlearning/uci_heart.py
COPY module3-fedlearning/datasets/ /srv/module3-fedlearning/datasets/
COPY server/synthesis/ ./

USER app

EXPOSE 8006

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006"]
