# Build context is the REPO ROOT (see docker-compose.yml), because some
# services import sibling modules. Build: docker build -f module3-fedlearning/Dockerfile .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 app
WORKDIR /srv/module3-fedlearning
COPY module3-fedlearning/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY module3-fedlearning/ ./
USER app
EXPOSE 8080
CMD ["python", "server.py", "--address", "0.0.0.0:8080"]
