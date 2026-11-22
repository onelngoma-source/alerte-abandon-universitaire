# Guide de passation (direction informatique)

Ce guide s'adresse à la personne qui reprend l'outil après son auteur : l'installer, le mettre à jour, le
sauvegarder, le dépanner, le faire évoluer. Il complète le guide de mise en service (`GUIDE_MISE_EN_SERVICE.md`),
qui traite du cadre légal, de l'organisation et du premier démarrage.

## 1. L'essentiel en cinq minutes

- Application **Flask** (Python 3.12), base **PostgreSQL** en production (SQLite pour les essais).
- Le schéma de la base évolue par **migrations** (Alembic, dossier `migrations/`), appliquées **automatiquement au
  démarrage**. On ne crée ni ne modifie jamais une table à la main.
- Le calcul du risque (dossier `moteur/` et fichier `models/modeles.joblib`) vient d'un protocole de recherche publié.
  On n'y touche pas sans refaire ce protocole (section 9).
- Trois commandes à connaître : `python -m outils.sauvegarde`, `python -m outils.comptes`, `python -m outils.synchroniser`.
- Avant toute mise à jour : **sauvegarde vérifiée**. Après : **`/sante`**.
- Toute modification du code passe par les tests (`python -m pytest -q`), lancés aussi par GitHub à chaque envoi.

## 2. Carte du code

| Dossier ou fichier | Contenu | Prudence |
|---|---|---|
| `app.py` | création de l'application, en-têtes de sécurité, sonde `/sante` | |
| `auth.py` | comptes, rôles, connexion, verrouillage, CSRF | toute modification se teste (`tests/test_durcissement.py`, `tests/test_suivi.py`) |
| `db.py` | description des tables, connexion, paramètres | toute modification de table appelle une migration (section 5) |
| `migrations/` | historique du schéma (Alembic) | ne jamais modifier une migration déjà déployée |
| `moteur/` | calcul du risque, facteurs, pistes d'accompagnement | voir section 9 |
| `metier/` | règles de suivi (dossiers, échéances), journal, raccordement | |
| `volets/` | pages et API, une par fonction de l'outil | |
| `templates/`, `static/` | écrans (HTML, CSS, JavaScript) | scripts en ligne : attribut `nonce` obligatoire (section 8) |
| `outils/` | sauvegarde, synchronisation, rappels, console de comptes | |
| `scripts/` | entraînement et recalibrage du modèle | |
| `tests/` | suite de tests (section 10) | |
| `models/`, `data/` | modèle entraîné, jeu de test | versions de numpy et scikit-learn figées (`requirements.txt`) |

## 3. Travailler sur le code

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium          # pour les tests d'interface
python -m pytest -q                            # toute la suite, sur SQLite
TEST_DATABASE_URL=postgresql://utilisateur@localhost/alerte_test python -m pytest -q   # la même, sur PostgreSQL
MODE_DEMO=1 python app.py                      # démonstration locale sur http://127.0.0.1:5000
```

Les tests de restauration PostgreSQL utilisent en plus une base `alerte_essai`, sur le même serveur que
`TEST_DATABASE_URL`.

## 4. Mettre à jour la production

1. `python -m outils.sauvegarde creer --verifier` : la commande doit afficher « vérifiée ».
2. Récupérer la nouvelle version (`git pull`), puis `pip install -r requirements.txt`.
3. Redémarrer le service : les migrations s'appliquent au démarrage. Un verrou PostgreSQL garantit qu'un seul
   processus les applique quand plusieurs démarrent en même temps.
4. Contrôler `https://.../sante` : `"etat": "ok"` et `"schema_a_jour": true`.
5. En cas de problème : revenir à la version précédente du code et restaurer la sauvegarde de l'étape 1 (section 6).

## 5. Faire évoluer la base

```bash
# 1. modifier la description des tables dans db.py
# 2. produire la migration, puis la RELIRE (renommages, valeurs par défaut, données à reprendre)
alembic revision --autogenerate -m "ajout de la date de naissance"
# 3. vérifier : le test compare le schéma obtenu par les migrations à celui de db.py
python -m pytest -q tests/test_durcissement.py
```

Règles : une migration déjà déployée ne se modifie plus, on en ajoute une nouvelle ; une colonne obligatoire
ajoutée à une table qui contient des données reçoit une valeur par défaut ; `alembic current` donne la révision
d'une base, `alembic history` la liste des migrations.

## 6. Sauvegardes

| Commande | Effet |
|---|---|
| `python -m outils.sauvegarde cle` | tire une clé de chiffrement, à placer dans `SAUVEGARDE_CLE` et dans un coffre hors du serveur |
| `python -m outils.sauvegarde creer --verifier` | sauvegarde complète, chiffrée et scellée, puis restauration d'essai dans une base vierge ; garde les 30 dernières |
| `python -m outils.sauvegarde verifier FICHIER` | refait l'essai de restauration sur un fichier précis |
| `python -m outils.sauvegarde restaurer FICHIER` | restaure dans la base configurée (refuse une base non vide, sauf `--forcer`) |

Une sauvegarde est **scellée** : la moindre modification du fichier (un seul bit) empêche son déchiffrement, et
chaque table porte une empreinte vérifiée à la restauration. Elle est **indépendante du moteur** : une sauvegarde
PostgreSQL se vérifie dans SQLite et peut servir à changer de serveur. **Sans la clé, les sauvegardes sont
illisibles** : la perdre revient à les perdre. Pour PostgreSQL, un `pg_dump` quotidien reste un bon complément.
La page « Données » et la sonde `/sante` signalent une sauvegarde absente, non vérifiée ou vieille de plus d'un jour.

## 7. Raccordement au logiciel de scolarité

Deux voies, au choix ; dans les deux, renvoyer un fichier ne crée aucun doublon (le matricule identifie l'étudiant
dans sa promotion) et chaque import est tracé dans le journal.

- **API.** Page « Données » : créer un jeton de service (affiché une seule fois, seule son empreinte est gardée).
  Le logiciel de scolarité envoie :
  `curl -H "Authorization: Bearer aap_..." -F promotion="Licence 1 2026-2027" -F fichier=@l1.csv https://.../api/v1/synchronisation`.
  Un jeton se révoque d'un clic ; cinq essais de jetons faux depuis une adresse la bloquent cinq minutes.
- **Dossier de dépôt.** Le logiciel dépose `<Nom de la promotion>.csv` dans `DEPOT_SCOLARITE` ;
  `python -m outils.synchroniser` (planifié) importe, range dans `traites/`, et place les fichiers refusés dans
  `erreurs/` avec un `.txt` qui explique pourquoi.

Format attendu : les colonnes du gabarit d'import (page « Importer », bouton « Gabarit vierge »), dont le matricule.

## 8. Sécurité : ce qu'il ne faut pas défaire

- **Scripts en ligne** : la politique de contenu (CSP) n'exécute que les scripts du site et les blocs `<script>`
  porteurs de `nonce="{{ csp_nonce }}"`. Un nouveau bloc sans cet attribut ne s'exécute pas (le test d'interface
  échoue). Ne jamais ajouter `'unsafe-inline'` ou `'unsafe-eval'` à `script-src`.
- **Adresse des visiteurs** : ne jamais relire `X-Forwarded-For` à la main ; régler `PROXYS_DE_CONFIANCE`.
- **Requêtes SQL** : toujours par SQLAlchemy, jamais de texte construit avec une saisie.
- **HTML construit en JavaScript** : toute donnée passe par `Commun.echapper()`.
- **Nouvelle route** : `@connexion_requise` ou `@role_requis(...)`, et `interdit_en_demo` si elle modifie des données
  réelles ; une route qui modifie quelque chose est protégée par le jeton CSRF automatiquement.

## 9. Le modèle de risque

Version affichée dans « Données » et « Fiabilité ». Deux gestes possibles :

- **Recalibrer** (les probabilités dérivent, le classement reste bon) : `python scripts/recalibrer.py`, sur des
  promotions dont le devenir réel est connu. Voir la section 7 du guide de mise en service.
- **Réentraîner** (nouvelles variables, données locales) : refaire le protocole du projet de recherche
  (github.com/onelngoma-source/abandon-universitaire), avec validation temporelle et vérification de l'équité,
  avant de remplacer `models/modeles.joblib`.

Ne changez pas les versions de numpy ou de scikit-learn sans réentraîner : le modèle deviendrait illisible.

## 10. Gestes de secours

| Situation | Geste |
|---|---|
| Plus aucun administrateur ne peut se connecter | `python -m outils.comptes reinitialiser IDENTIFIANT` : mot de passe provisoire, à changer à la connexion |
| Un compte est bloqué après des erreurs de saisie | attendre 15 minutes, ou `python -m outils.comptes debloquer IDENTIFIANT` |
| `/sante` répond 503 | la base ne répond pas : vérifier PostgreSQL, l'espace disque, `DATABASE_URL` |
| `/sante` : `schema_a_jour` à `false` | une migration a échoué au démarrage : lire le journal du service, corriger, redémarrer |
| Fuite ou intrusion soupçonnée | révoquer tous les jetons de service ; changer `FLASK_SECRET_KEY` (déconnecte tout le monde) ; réinitialiser les mots de passe ; lire le journal (« Journal ») ; notifier l'APDPVP sans délai |
| Perte du serveur | nouveau serveur, `SAUVEGARDE_CLE` depuis le coffre, `python -m outils.sauvegarde restaurer DERNIER_FICHIER` |

## 11. Ce que les tests prouvent

| Garantie | Test |
|---|---|
| Le schéma des migrations est identique à celui du code | `test_durcissement.py::test_les_migrations_produisent_exactement_le_schema_du_code` |
| Une base d'une version antérieure est reprise sans perte | `test_durcissement.py::test_une_base_d_avant_les_migrations_est_reprise_sans_perte` |
| Le verrouillage vaut pour tous les processus et survit au redémarrage | `test_durcissement.py::test_le_verrouillage_survit_a_un_redemarrage_et_vaut_pour_tous_les_processus` |
| Un en-tête falsifié ne contourne pas le verrouillage | `test_durcissement.py::test_un_en_tete_falsifie_ne_contourne_pas_le_verrouillage` |
| Un compte attaqué depuis plusieurs adresses est protégé | `test_durcissement.py::test_un_compte_vise_depuis_plusieurs_adresses_est_protege` |
| Les scripts injectés ne s'exécutent pas (CSP à nonce) | `test_durcissement.py::test_en_tetes_de_securite_et_nonce_de_script`, et chaque test d'interface |
| Une sauvegarde se restaure à l'identique | `test_sauvegarde.py::test_la_sauvegarde_se_restaure_a_l_identique` |
| Toute altération d'une sauvegarde est détectée | `test_sauvegarde.py::test_une_valeur_modifiee_dans_le_fichier_est_detectee`, `..._chiffree_et_scellee`, `..._tronque_...` |
| Un jeton n'est jamais stocké ; révoqué, il ne sert plus | `test_raccordement.py` |
| Les droits par rôle, le CSRF, le journal | `test_suivi.py` |
| Les calculs et le protocole d'évaluation | `test_protocole.py`, `test_import_identique.py`, `test_saisie_et_base.py` |
| Le parcours réel dans un navigateur | `test_interface.py` |

## 12. Liste de passation

- [ ] Accès au dépôt GitHub, au serveur, à la base, au coffre (clé des sauvegardes, `FLASK_SECRET_KEY`)
- [ ] Suite de tests lancée sur un poste de travail, verte
- [ ] Une sauvegarde créée, vérifiée, puis **restaurée pour de bon** sur une machine d'essai
- [ ] Une mise à jour faite selon la section 4 sur la machine d'essai
- [ ] Un compte réinitialisé avec la console de secours
- [ ] Sonde `/sante` branchée sur la supervision ; tâches planifiées en place (sauvegarde, rappels, synchronisation)
- [ ] Contact de l'auteur et du délégué à la protection des données notés
