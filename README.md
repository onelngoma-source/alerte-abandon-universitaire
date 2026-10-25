# Dispositif d'alerte précoce : risque d'abandon universitaire

Application de démonstration du mémoire (approche non paramétrique à noyau comparée au Machine Learning).
Elle a trois volets, qui correspondent à trois modules du code (dossier `volets/`).

| Volet | Page | Rôle |
|---|---|---|
| 1. Tableau de bord | `/tableau` | Les 1 328 étudiants du jeu de test (jamais vus à l'entraînement), leur risque selon le noyau et la forêt aléatoire, filtres en colonne, tri, export, indicateurs, graphique du risque par filière. **Un clic sur une ligne ouvre la fiche de l'étudiant** : deux estimations, les 5 étudiants au profil le plus proche, facteurs qui pèsent sur le risque, conseils, devenir réel et justesse des estimations |
| 2. Saisie individuelle | `/saisie` | Un étudiant, 13 champs, résultat des deux modèles, 5 profils voisins, facteurs, pistes d'accompagnement ; 2e semestre facultatif |
| 3. Import CSV | `/import` | Un fichier produit le **même tableau** que le tableau de bord (même code de calcul, même gabarit d'affichage). La correspondance des colonnes couvre les **36 variables** (13 principales, 23 dans une section repliée), avec suggestion automatique des noms identiques ou proches |

## Lancer l'application

```bash
pip install -r requirements.txt
python app.py                      # http://localhost:5000  (compte : admin / changez-moi)
# serveur de production : gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT app:app
```

Variables d'environnement : `FLASK_SECRET_KEY`, `ADMIN_IDENTIFIANT`, `ADMIN_MDP_HACHE` (hash werkzeug),
`DB_PATH` (fichier SQLite, `instance/alerte.db` par défaut), `FOND_CONNEXION` et `FOND_VOILE` (image de fond de la page de connexion), `DEMO_PRELOAD` (par défaut `1` : les 1 328 étudiants de test sont déjà chargés au lancement ; `0` pour démarrer avec une base vide), `DUREE_SESSION_HEURES` (durée de validité de la connexion, 8 heures par défaut).

Sans `FLASK_SECRET_KEY`, une clé aléatoire est tirée à chaque démarrage : relancer l'application
déconnecte donc tout le monde. C'est le moyen le plus simple de retrouver la page de connexion.

## Scénario de démonstration (5 minutes)

1. Tableau de bord : les 1 328 étudiants de test sont déjà affichés au lancement (la base peut être vidée puis rechargée avec le bouton « Charger le jeu de test »).
2. La carte « Performances des modèles » (repliée par défaut) retombe sur le mémoire : AUC 0,875 et 0,934, accuracy, F1.
3. Filtres : filière, débiteur, risque, « les deux modèles divergent ». Les indicateurs et graphiques suivent.
4. Saisie individuelle : « Remplir un exemple », puis lecture des facteurs et des conseils.
5. Import CSV : « Télécharger le fichier du jeu de test », l'importer : le tableau obtenu est identique au tableau de bord.
   Importer ensuite `tests/fixtures/import_colonnes_differentes.csv` pour montrer l'étape de correspondance des colonnes.
6. Retour au tableau : un clic sur une ligne ouvre la fiche d'explication de l'étudiant.

## Organisation du code

```
app.py              création de l'application, enregistrement des volets
auth.py             connexion (compte unique)
db.py               base SQLite (sqlite3), schéma et requêtes
moteur/scoring.py   calcul unique : nettoyage, estimation des variables absentes, noyau, forêt aléatoire, SHAP
moteur/cohortes.py  construction d'une cohorte (jeu de test ou fichier) : une seule fonction, `importer`
moteur/conseils.py  pistes d'accompagnement
volets/             un module par volet (tableau, saisie, import_csv) + api_cohortes (commune)
templates/, static/ Tabler (Bootstrap 5), Chart.js et les polices (Inter, Space Grotesk), copiés en local :
                    aucune dépendance externe à l'exécution
static/js/effets.js onde au clic et voile de chargement, partagés par toutes les pages
static/js/connexion.js animations de la page de connexion (décoratif)
data/, models/      jeu de données UCI, jeu de test (1 328), modèles entraînés (notebooks/)
tests/              42 tests (pytest)
```

## Identité visuelle

Palette : bleu `#3281E0`, bleu profond `#0D3863` (barre de navigation, bandeaux), jaune pâle `#F7FFBD` (onglet actif,
profils synthétiques), fonds `#F4F6FA`. Titres en Space Grotesk, texte en Inter, les deux servis depuis
`static/vendor/fonts/` (aucun appel réseau). Formes arrondies, boutons en pilule.
Le vert, l'orange et le rouge restent réservés aux niveaux de risque : ce sont les seules couleurs porteuses de sens.

Verre dépoli (`backdrop-filter`) là où un élément flotte au-dessus d'un fond coloré : barre de navigation,
barre de cohorte, fiche de l'étudiant, voile de chargement. Les cartes de données et les tableaux restent opaques.
Boutons avec relief au survol et onde au clic (`static/js/effets.js`).
Page de connexion animée : halos qui dérivent, lueur qui suit le curseur et chiffres du dispositif qui s'en échappent
(`static/js/connexion.js`). Le voile de chargement, en verre dépoli, couvre la connexion, l'estimation d'un profil,
l'import d'un fichier et le chargement du jeu de test.
Tous ces effets respectent `prefers-reduced-motion` et aucun ne touche au calcul.

## Changer l'image de fond de la page de connexion

Déposez une image nommée `connexion.jpg` (ou `.png`, `.webp`, `.avif`) dans `static/fonds/`, puis rechargez la page :
elle est prise en compte aussitôt, sans toucher au code. Retirez le fichier pour revenir au dégradé bleu.
L'image s'affiche telle quelle : rien n'est écrit directement dessus, le texte vivant dans la carte et dans le volet bleu.
Deux réglages facultatifs : `FOND_CONNEXION` désigne un autre fichier du dossier (ou une adresse `https://`),
et `FOND_VOILE` assombrit l'image de 0 à 90 (0 par défaut, à monter si une image claire noie la carte). Le détail est rappelé dans
`static/fonds/LISEZ-MOI.txt`.

## Modèle de données (SQLite)

`COHORTE (id, nom, origine, fichier, effectif, ignorees, date_creation)` 1-n
`ETUDIANT (id, #cohorte_id, reference, filiere, genre, age, boursier, debiteur, frais_a_jour, note_s1, note_s2, devenir_reel, abandon_reel, caracteristiques)` 1-2
`SCORE (#etudiant_id, modele, probabilite, categorie, mode_calcul)`, clé primaire (etudiant_id, modele).
Le jeu de test et chaque fichier importé sont des cohortes : le tableau de bord affiche l'une ou l'autre.
`caracteristiques` conserve les valeurs fournies des 36 variables (JSON) : c'est ce qui permet de recalculer l'explication d'un étudiant à la demande.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

Ils vérifient : la séparation du mémoire (3 096 / 1 328 / 427 abandons), les indicateurs du mémoire, la non-régression
contre l'application d'origine (56 profils), l'identité tableau de bord / import (ordre des colonnes, séparateur, virgule décimale,
correspondance manuelle), la saisie, la base, l'explication du noyau (le calcul à la main sur les voisins redonne la probabilité du modèle pour les 1 328 étudiants, en mode complet et précoce) et le rendu réel dans un navigateur.

## Ce que l'écran n'affiche volontairement pas

L'application s'adresse à des conseillers, pas à des statisticiens. Les détails de calcul sont donc absents de l'écran
et expliqués dans le document de référence (à l'oral lors de la soutenance) : les 75 voisins, leurs poids et la largeur de bande,
la part de profils synthétiques (SMOTE), les valeurs SHAP, l'estimation des variables absentes, le détail du mode précoce
et le codage des 23 variables supplémentaires. Les calculs sont inchangés ; seul l'affichage est simplifié.

## Limites assumées

- Un fichier qui ne contient que les 13 champs du formulaire est calculé, mais 23 variables sont alors estimées : le tableau
  n'est pas identique à celui des 36 variables (écart affiché dans le compte rendu de l'import).
- Les 23 variables supplémentaires suivent le codage portugais du jeu d'origine : pour des données locales, elles n'ont de sens que si elles sont recodées de la même façon.
- Les modèles ont été entraînés sur des données portugaises : aucun résultat n'est établi pour le Gabon (Chapitre IV, limites).
- Le noyau est explicable par ses voisins, mais il s'appuie sur 75 voisins dont environ un quart sont des profils synthétiques créés par SMOTE ; l'écran n'en montre que 5 (étiquetés « Synthétique » le cas échéant), qui portent en moyenne 63 % du poids. SHAP n'explique que le Random Forest.
- Compte administrateur unique, adapté à une démonstration ; à durcir avant tout usage réel.
- **Les probabilités affichées ne sont pas calibrées.** SMOTE porte le taux d'abandon de l'apprentissage de 32,11 % à
  50 %, donc les modèles surestiment le risque : probabilité moyenne annoncée sur le jeu de test de 38,9 % pour le
  noyau, 36,2 % pour la forêt et 40,3 % pour la régression logistique, contre 32,15 % réellement observés. Concrètement,
  les étudiants pour qui le noyau annonce 50 à 60 % abandonnent en réalité à 37,3 %. Le chiffre affiché se lit donc
  comme un *indice de priorité*, pas comme une fréquence attendue.
  Ce défaut ne touche aucun résultat du mémoire : le recalibrage est une transformation monotone et laisse l'AUC
  inchangée (vérifié sur les quatre modèles). Les trois catégories de risque restent correctement ordonnées, la
  catégorie « élevé » de la forêt contenant 345 étudiants dont 89,6 % abandonnent réellement.
  La correction est volontairement **non appliquée** : à seuils constants (0,30 / 0,60) elle reclasserait 248 des
  1 328 étudiants et ferait tomber la catégorie « élevé » de 345 à 253, soit 92 alertes de moins. Elle suppose donc
  de réajuster les seuils dans le même mouvement. Mesures reproductibles : `scripts/calibration.py`.
