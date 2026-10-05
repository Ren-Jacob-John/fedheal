# Build context is the REPO ROOT (see docker-compose.yml), because some
# services import sibling modules. Build: docker build -f module7-admin/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 app
WORKDIR /srv/module7-admin
COPY module7-admin/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY module3-fedlearning/ /srv/module3-fedlearning/
COPY module7-admin/ ./
USER app
EXPOSE 8005
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
