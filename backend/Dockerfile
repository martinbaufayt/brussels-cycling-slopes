# Image Python légère basée sur Debian slim
# On choisit une version fixe (3.12) pour la reproductibilité
FROM python:3.12-slim

# Répertoire de travail dans le conteneur
WORKDIR /app

# On copie d'abord requirements.txt SEUL, avant le reste du code.
# Pourquoi ? Docker construit l'image par couches (layers).
# Si on copie tout d'un coup, chaque changement de code déclenche
# une réinstallation des dépendances. En séparant, la couche pip
# est mise en cache et réutilisée tant que requirements.txt ne change pas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensuite seulement on copie le code de l'application
COPY . .

# Port exposé par le conteneur (FastAPI écoute sur 8000)
EXPOSE 8000

# Commande de démarrage
# --host 0.0.0.0 : écoute sur toutes les interfaces réseau du conteneur
#                  (pas seulement localhost, sinon Docker ne peut pas forwarder)
# --reload       : redémarre automatiquement quand le code change (dev uniquement)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
