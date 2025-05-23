FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "src.cleeroute.main:app", "--host", "0.0.0.0", "--port", "8000"]

# s'authentifier
#docker login
# pour construire l'image docker
# docker build -t cleeroute_image .
# pour lancer le conteneur
# docker run -p 8000:8000 cleeroute_image:v0
# pour lancer le conteneur en mode interactif
# docker run -it -p 8000:8000 cleeroute /bin/bash
# pour lancer le conteneur en mode interactif avec un terminal
# docker run -it -p 8000:8000 cleeroute /bin/bash