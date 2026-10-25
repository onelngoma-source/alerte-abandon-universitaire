# Application complète, à jour

Ce dossier est l'application entière, prête à être poussée sur Hugging Face Spaces. Il n'y a
rien à copier depuis une version précédente : tout est déjà en place.

## Vérifier que tout est là

```bash
python3 -m pytest tests/ -q
```

Attendu : `50 passed`. C'est le résultat obtenu depuis ce dossier avant l'envoi.

## Lancer en local

Comportement habituel, avec tous les boutons :

```bash
python3 app.py
```

Comportement de la version en ligne, cohortes cloisonnées et boutons destructeurs masqués :

```bash
MODE_DEMO=1 python3 app.py
```

Dans les deux cas, `http://localhost:5000`.

## Ce qui a changé depuis la version que tu avais

Le **mode démonstration**, ajouté pour que trois jurés puissent se connecter en même temps
sans se gêner. Il ne s'active que si la variable d'environnement `MODE_DEMO` vaut `1`, ce que
fait le `Dockerfile` pour la version en ligne et rien d'autre. En local, sans cette variable,
l'application est identique à ce qu'elle était.

Huit fichiers portent cette modification :

| Fichier | Apport |
|---|---|
| `db.py` | colonne `proprietaire` sur la table `cohorte`, avec migration automatique de la base existante ; lectures et suppressions filtrées sur le propriétaire ; SQLite en mode WAL avec attente de 15 s sur les verrous |
| `auth.py` | la variable `MODE_DEMO` et la fonction `proprietaire_courant()`, qui attribue un jeton tiré au hasard à chaque navigateur |
| `moteur/cohortes.py` | le propriétaire est enregistré à l'import |
| `volets/tableau.py` | le tableau de bord ne liste que la cohorte partagée et celles du visiteur |
| `volets/import_csv.py` | l'import rattache la cohorte à son visiteur |
| `volets/api_cohortes.py` | suppression d'une cohorte d'autrui refusée (403), vidage de la base refusé (403), lecture d'une cohorte d'autrui refusée (404) |
| `templates/tableau.html` | les deux boutons destructeurs ne sont rendus que hors mode démonstration |
| `tests/test_mode_demonstration.py` | fichier nouveau, huit tests qui simulent trois visiteurs |

La suite de tests passe donc de 42 à 50 tests.

## Les fichiers ajoutés pour la mise en ligne

| Fichier | Rôle |
|---|---|
| `Dockerfile` | recette de construction de l'image, lue automatiquement par Hugging Face |
| `requirements.txt` | **il remplace l'ancien** : les versions y sont figées, parce que les modèles sont sérialisés avec scikit-learn 1.8.0, numpy 2.5.3 et joblib 1.6.0 |
| `.dockerignore` | exclut de l'image les caches, le dossier `tests/` et la base locale `instance/` |
| `DEPLOIEMENT.md` | les étapes de la mise en ligne, dans l'ordre |
| `qr_soutenance.py` | fabrique le carton QR une fois l'adresse connue |
| `QR_application.png`, `QR_seul.png` | exemples produits par ce script, à refaire avec l'adresse définitive |

`requirements-dev.txt` est inchangé : il sert aux tests, pas à la production.

## Ce qui n'est pas dans le dossier, et pourquoi

**La base `instance/alerte.db`.** Elle se reconstruit toute seule au démarrage à partir de
`data/jeu_de_test_1328.csv`, en 4,4 secondes mesurées. Il n'y a donc rien à sauvegarder ni à
transporter. C'est `.gitignore` et `.dockerignore` qui l'excluent.

**Les caches Python** et `.pytest_cache`, qui se régénèrent.
