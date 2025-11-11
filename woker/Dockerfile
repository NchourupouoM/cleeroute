# worker/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["celery", "-A", "src.cleeroute.tasks", "worker", "--loglevel=info", "--pool=solo"]
