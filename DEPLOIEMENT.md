# Mettre la démonstration en ligne sur Render

Objectif : une adresse publique, stable, gratuite, que le jury peut ouvrir depuis son téléphone.
Ce document concerne la **démonstration** (`MODE_DEMO=1`, base SQLite éphémère, comptes fictifs). Pour une installation
réelle dans un établissement (PostgreSQL, HTTPS, comptes nominatifs, rappels), suivre le
[guide de mise en service](GUIDE_MISE_EN_SERVICE.md).

En démonstration, la page de connexion propose quatre comptes fictifs (administrateur, responsable, deux conseillers,
mot de passe « demo ») et le suivi est déjà engagé sur les cohortes 2015 à 2017. Le compte du jury, déclaré par
`ADMIN_IDENTIFIANT` et `ADMIN_MDP_HACHE`, s'y ajoute avec le rôle d'administrateur. Comme la base est recréée à chaque
redémarrage du service, ce que les visiteurs modifient disparaît au réveil suivant.

---

## Pourquoi Render, et plus Hugging Face

Hugging Face a rendu les Spaces **Docker** et **Gradio** payants. Seuls les Spaces *Static* restent
gratuits, et un Static ne sert que des fichiers : il ne peut pas faire tourner une application Flask.

Render reste gratuit, sans carte bancaire, avec **512 Mo de mémoire**. La pointe mesurée de cette
application en démonstration, après un parcours complet des pages par trois comptes, est de **363 Mo**. La marge suffit largement à plusieurs visiteurs simultanés.

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

**Gardez `FLASK_SECRET_KEY`.** C'est elle qui signe les cookies de session. Sans elle, l'application tire
une clé une fois et la garde dans sa base ; mais sur l'offre gratuite de Render la base SQLite repart de zéro
à chaque redéploiement, et tous les jurés seraient alors déconnectés. Sur Render, l'adresse réelle des
visiteurs est reprise automatiquement derrière le proxy de l'hébergeur (`PROXYS_DE_CONFIANCE` vaut 1 par défaut).

Puis **Create Web Service**. La première construction prend cinq à dix minutes.

### 6. Vérifier

L'adresse obtenue a la forme `https://alerte-abandon-universitaire.onrender.com`.

Ouvre-la, identifie-toi avec `jury` et ton mot de passe, et vérifie que le tableau de bord affiche les
1 227 étudiants (cohortes 2015 à 2017).

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

Le `Dockerfile` active `MODE_DEMO=1`. Ce mode permet à plusieurs personnes (jurés, recruteurs) d'essayer l'outil
en même temps, dans chacun des trois rôles.

**Des comptes fictifs prêts à l'emploi.** Administrateur, responsable, deux conseillers, mot de passe « demo »,
proposés en un clic sur la page de connexion. Le compte du jury s'y ajoute.

**Un suivi déjà engagé.** 455 dossiers ouverts par la règle d'alerte sur les cohortes 2015 à 2017, dont 260 déjà
attribués et plus ou moins avancés (contacts, entretiens, tutorats, clôtures), avec des dates étalées sur quarante
jours : les pages « Dossiers » et « Pilotage » ont de quoi montrer.

**Rien de destructeur.** Suppression de la promotion de démonstration, vidage de la base, création ou modification
de comptes et purge répondent 403, même appelés directement.

Ces garanties sont couvertes par les tests de `tests/test_mode_demonstration.py`.

---

## Les trois points de vigilance

**Le réveil d'une minute.** C'est le point le plus important. **Ouvre l'application depuis ton téléphone
une heure avant la soutenance** pour la réveiller, et reconnecte-toi dix minutes avant pour qu'elle ne se
soit pas rendormie. Quinze minutes d'inactivité suffisent à la renvoyer en veille.

**Le système de fichiers est éphémère.** Tout ce qu'un visiteur modifie (dossiers, imports) disparaît au prochain
redémarrage. Ce n'est pas un défaut ici : la base de démonstration se reconstruit seule en 3 secondes environ à
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
