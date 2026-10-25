# Image de deploiement du dispositif d'alerte precoce.
# Independante de l'hebergeur : le port est lu dans la variable PORT, que Render,
# Fly, Koyeb, Cloud Run et Hugging Face renseignent chacun a leur maniere.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000 \
    MODE_DEMO=1

WORKDIR /app

# libgomp est requis par scikit-learn (OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Certains hebergeurs executent le conteneur avec un utilisateur non root :
# le dossier de la base doit rester inscriptible.
RUN mkdir -p instance && chmod -R 777 instance

EXPOSE 10000

# Forme shell, et non exec, pour que ${PORT} soit bien substitue au demarrage.
# MODE_DEMO=1 : cohortes cloisonnees par visiteur, suppression et vidage desactives.
# 1 worker et 4 threads : les modeles sont charges une seule fois en memoire
# (358 Mo mesures en pointe), et les trois jures sont servis par les threads.
CMD gunicorn -w 1 --threads 4 --timeout 120 -b 0.0.0.0:${PORT:-10000} app:app
