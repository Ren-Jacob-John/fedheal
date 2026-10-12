
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# Install the system library required by LightGBM
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app

WORKDIR /srv/module8-synthesis

COPY module8-synthesis/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY module5-modelzoo/ /srv/module5-modelzoo/
COPY module6-condition-router/ /srv/module6-condition-router/
COPY module3-fedlearning/uci_heart.py /srv/module3-fedlearning/uci_heart.py
COPY module3-fedlearning/datasets/ /srv/module3-fedlearning/datasets/
COPY module8-synthesis/ ./

USER app

EXPOSE 8006

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8006"]
