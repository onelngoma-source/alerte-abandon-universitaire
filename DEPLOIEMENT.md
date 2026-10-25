# Mettre l'application en ligne sur Render

Objectif : une adresse publique, stable, gratuite, que le jury peut ouvrir depuis son téléphone.

---

## Pourquoi Render, et plus Hugging Face

Hugging Face a rendu les Spaces **Docker** et **Gradio** payants. Seuls les Spaces *Static* restent
gratuits, et un Static ne sert que des fichiers : il ne peut pas faire tourner une application Flask.

Render reste gratuit, sans carte bancaire, avec **512 Mo de mémoire**. La pointe mesurée de cette
application, en la poussant avec SHAP, le tableau de bord complet et dix allers-retours, est de
**358 Mo**. Il reste donc 154 Mo de marge, ce qui suffit largement à trois jurés simultanés.

Deux contreparties à connaître.

**Le service s'endort après 15 minutes sans visite**, et le réveil prend **environ une minute**.
C'est plus long que la plupart des hébergeurs. Il faudra réveiller l'application avant la soutenance.

**Render déploie depuis un dépôt GitHub**, et non depuis son propre dépôt. Il faut donc créer un dépôt
GitHub au passage. Ce n'est pas du temps perdu : cela rend le code consultable, ce qui est un argument
devant un jury.

---

## Les étapes

### 1. Créer le dépôt GitHub

Sur **github.com**, crée un compte si tu n'en as pas, puis **New repository** :

| Champ | Valeur |
|---|---|
| Repository name | `alerte-abandon-universitaire` |
| Visibility | **Public** |
| Initialize with README | décoché |

Public est sans risque : aucun secret ne figure dans le code. Le mot de passe du jury n'y est présent
ni en clair ni sous forme d'empreinte, il sera fourni à Render par variable d'environnement.

### 2. Envoyer le code

Depuis le dossier de l'application, sur ta machine :

```bash
git init
git add .
git commit -m "Dispositif d'alerte precoce du risque d'abandon universitaire"
git branch -M main
git remote add origin https://github.com/TON-COMPTE/alerte-abandon-universitaire.git
git push -u origin main
```

Git demandera un identifiant : donne ton nom d'utilisateur GitHub, et comme mot de passe un **jeton
d'accès personnel**, créé dans *Settings → Developer settings → Personal access tokens → Tokens
(classic)*, avec la portée `repo`.

Les modèles pèsent 33 Mo au total, ce qui passe sans Git LFS.

### 3. Fabriquer les deux chaînes de configuration

Sur ta machine :

```bash
python3 -c "from werkzeug.security import generate_password_hash as g; print(g('soutenance2026'))"
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Sous Windows, remplace `python3` par `py`.

La première sort une longue chaîne commençant par `scrypt:` ou `pbkdf2:`. C'est l'**empreinte** du mot
de passe du jury : l'application n'accepte jamais un mot de passe en clair dans sa configuration.
La seconde est la clé de signature des sessions.

### 4. Créer le service sur Render

Sur **render.com**, crée un compte, puis **New → Web Service**, et connecte ton dépôt GitHub.

| Champ | Valeur |
|---|---|
| Name | `alerte-abandon-universitaire` |
| Language | **Docker** |
| Branch | `main` |
| Instance Type | **Free** |
| Health Check Path | `/connexion` |

Render détecte le `Dockerfile` à la racine et s'en sert. Le port est transmis par la variable `PORT`,
que le `Dockerfile` lit déjà : il n'y a rien à régler de ce côté.

### 5. Déclarer les variables d'environnement

Toujours dans la création du service, section **Environment Variables**, ajoute trois entrées :

| Nom | Valeur |
|---|---|
| `FLASK_SECRET_KEY` | la chaîne de 64 caractères de l'étape 3 |
| `ADMIN_IDENTIFIANT` | `jury` |
| `ADMIN_MDP_HACHE` | l'empreinte `scrypt:` de l'étape 3 |

**Sans `FLASK_SECRET_KEY`, une clé au hasard est tirée à chaque démarrage.** Comme c'est elle qui signe
les cookies de session, tous les jurés seraient déconnectés à chaque redémarrage, et chacun perdrait
l'accès à la cohorte qu'il venait d'importer.

Puis **Create Web Service**. La première construction prend cinq à dix minutes.

### 6. Vérifier

L'adresse obtenue a la forme `https://alerte-abandon-universitaire.onrender.com`.

Ouvre-la, identifie-toi avec `jury` et ton mot de passe, et vérifie que le tableau de bord affiche les
1 328 étudiants.

Si la construction échoue, lis les logs de bas en haut : la vraie erreur est presque toujours la
dernière ligne rouge.

| Message | Cause | Correction |
|---|---|---|
| `ModuleNotFoundError` | un paquet manque dans `requirements.txt` | l'ajouter avec sa version, repousser |
| `unable to open database file` | dossier `instance` non inscriptible | vérifier la ligne `chmod -R 777 instance` |
| `FileNotFoundError: models/...` | dossier `models/` non poussé | `git status`, puis `git add models/` |
| `libgomp.so.1: cannot open...` | OpenMP absent | vérifier la ligne `apt-get install libgomp1` |

### 7. Fabriquer le carton QR

Une fois l'adresse définitive connue :

```bash
python3 qr_soutenance.py "https://alerte-abandon-universitaire.onrender.com" \
        --identifiant jury --motdepasse soutenance2026
```

Deux images sont produites : `QR_application.png`, le carton complet à projeter, et `QR_seul.png`, le
code seul à poser sur une diapositive existante.

---

## Le mode démonstration

Le `Dockerfile` active `MODE_DEMO=1`. Ce mode a été ajouté pour que trois jurés puissent se connecter en
même temps sans se gêner. Il change trois choses.

**Les cohortes sont cloisonnées par visiteur.** Chaque navigateur reçoit un identifiant propre. Un juré
qui importe un fichier est le seul à voir la cohorte qui en résulte, et le seul à pouvoir ouvrir les
fiches de ses étudiants.

**La cohorte de référence reste partagée.** Les 1 328 étudiants du jeu de test sont visibles de tous, en
lecture seule, et personne ne peut les supprimer.

**Les actions destructrices sont bloquées.** Les boutons « Supprimer cette cohorte » et « Vider la base »
disparaissent, et les routes correspondantes répondent 403 même appelées directement.

Huit tests automatisés couvrent ces garanties. En local, sans la variable `MODE_DEMO`, l'application se
comporte exactement comme avant.

---

## Les trois points de vigilance

**Le réveil d'une minute.** C'est le point le plus important. **Ouvre l'application depuis ton téléphone
une heure avant la soutenance** pour la réveiller, et reconnecte-toi dix minutes avant pour qu'elle ne se
soit pas rendormie. Quinze minutes d'inactivité suffisent à la renvoyer en veille.

**Le système de fichiers est éphémère.** Toute cohorte importée par un juré disparaît au prochain
redémarrage. Ce n'est pas un défaut ici : la base de référence se reconstruit seule en 4,4 secondes à
partir du CSV, et c'est même souhaitable pour une démonstration.

**750 heures par mois.** Un seul service en fonctionnement continu consomme 744 heures, donc le quota
tient. Mais ne crée pas un second service gratuit en parallèle.

---

## Le plan de repli

Si la salle n'a pas de réseau fiable, ou si le réveil pose problème, l'application peut tourner sur ton
propre ordinateur et être exposée par un tunnel, sans aucun compte à créer :

```bash
# terminal 1
python3 app.py
# terminal 2
cloudflared tunnel --url http://localhost:5000
```

Une adresse en `.trycloudflare.com` s'affiche, publique immédiatement. Mais elle **change à chaque
lancement**, donc le QR doit être fabriqué sur place, quelques minutes avant de passer.

Et dans tous les cas, la vidéo de démonstration intégrée au PowerPoint ne dépend d'aucune connexion.
