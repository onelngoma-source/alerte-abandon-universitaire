# Dispositif d'alerte précoce : risque d'abandon universitaire

Application de démonstration du projet « approche non paramétrique à noyau comparée au Machine Learning pour prédire
l'abandon universitaire », dans sa **version rigoureuse** : les modèles viennent du projet de recherche
[abandon-universitaire](https://github.com/onelngoma-source/abandon-universitaire) (découpage par cohorte, validation croisée
imbriquée, calibration vérifiée, seuil fixé par les coûts, test scellé ouvert une seule fois).
La version présentée lors de la soutenance est conservée dans l'historique Git (étiquette `version-soutenance`).

Chaque étudiant reçoit deux estimations :
- la **régression logistique**, modèle retenu : ses probabilités sont calibrées et c'est elle qui déclenche l'alerte ;
- l'**approche à noyau** (estimateur de Nadaraya-Watson), pour comparaison : elle s'explique par les étudiants qui lui ressemblent.

Le modèle est choisi selon l'information disponible : **à l'inscription (T0)**, **à la fin du 1er semestre (T1)** ou
**à la fin du 2e semestre (T2)**. L'alerte se déclenche quand la probabilité atteint **1 sur 6** : un abandon non détecté
coûte autant que 5 accompagnements inutiles.

L'application a trois volets, qui correspondent à trois modules du code (dossier `volets/`).

| Volet | Page | Rôle |
|---|---|---|
| 1. Tableau de bord | `/tableau` | Les 1 227 étudiants des cohortes 2015 à 2017 (jamais vus à l'entraînement), leur risque selon les deux modèles, filtres en colonne, tri, export, indicateurs, graphique du risque par filière. **Un clic sur une ligne ouvre la fiche de l'étudiant** : deux estimations, alerte, les 5 étudiants qui pèsent le plus dans l'estimation à noyau, facteurs qui pèsent sur le risque, conseils, devenir réel |
| 2. Saisie individuelle | `/saisie` | Un étudiant, 13 champs ; semestres facultatifs (le modèle T0, T1 ou T2 est choisi selon ce qui est rempli) |
| 3. Import CSV | `/import` | Un fichier produit le **même tableau** que le tableau de bord (même code de calcul, même gabarit d'affichage). La correspondance des colonnes couvre les **36 variables**, avec suggestion automatique des noms identiques ou proches |

## Lancer l'application

```bash
pip install -r requirements.txt
python app.py                      # http://localhost:5000  (compte : admin / changez-moi)
# serveur de production : gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT app:app
```

Variables d'environnement : `FLASK_SECRET_KEY`, `ADMIN_IDENTIFIANT`, `ADMIN_MDP_HACHE` (hash werkzeug),
`DB_PATH` (fichier SQLite, `instance/alerte.db` par défaut), `FOND_CONNEXION` et `FOND_VOILE` (image de fond de la page de connexion), `DEMO_PRELOAD` (par défaut `1` : les 1 227 étudiants de test sont déjà chargés au lancement ; `0` pour démarrer avec une base vide), `DUREE_SESSION_HEURES` (durée de validité de la connexion, 8 heures par défaut).

Sans `FLASK_SECRET_KEY`, une clé aléatoire est tirée à chaque démarrage : relancer l'application
déconnecte donc tout le monde. C'est le moyen le plus simple de retrouver la page de connexion.

## Scénario de démonstration (5 minutes)

1. Tableau de bord : les 1 227 étudiants des cohortes 2015 à 2017 sont déjà affichés au lancement.
2. Vue « Analyse », carte « Performances des modèles » : ROC-AUC 0,902 (régression logistique) et 0,865 (noyau), Brier,
   part des abandons détectés et des alertes justes au seuil d'alerte. Ce sont exactement les chiffres de l'évaluation finale
   pré-enregistrée du projet de recherche.
3. Filtres : filière, débiteur, risque, « les deux modèles divergent ». Les indicateurs et graphiques suivent.
4. Saisie individuelle : « Remplir un exemple », notamment « À l'inscription » (aucune note), puis lecture de l'alerte,
   des facteurs et des conseils.
5. Import CSV : « Télécharger le fichier du jeu de test », l'importer : le tableau obtenu est identique au tableau de bord.
6. Retour au tableau : un clic sur une ligne ouvre la fiche d'explication de l'étudiant.

## Organisation du code

```
app.py                      création de l'application, enregistrement des volets
auth.py                     connexion (compte unique)
db.py                       base SQLite (sqlite3), schéma et requêtes
moteur/scoring.py           calcul unique : nettoyage, choix du moment, valeurs absentes, deux modèles, explications
moteur/variables.py         variables par moment, copie conforme du projet de recherche
moteur/noyau.py             estimateur de Nadaraya-Watson
moteur/cohortes.py          construction d'une cohorte (jeu de test ou fichier) : une seule fonction, `importer`
moteur/conseils.py          pistes d'accompagnement
volets/                     un module par volet (tableau, saisie, import_csv) + api_cohortes (commune)
templates/, static/         Tabler (Bootstrap 5), Chart.js et les polices, copiés en local : aucune dépendance externe
scripts/entrainer_modeles.py  entraîne les modèles et vérifie qu'ils retrouvent l'évaluation finale
data/                       jeu de données UCI, jeu de test (cohortes 2015 à 2017)
models/modeles.joblib       les six modèles (deux par moment), bornes et valeurs par défaut
tests/                      tests pytest
```

## Les modèles

`scripts/entrainer_modeles.py` reprend exactement le protocole du projet de recherche :
- **développement** : cohortes 2008 à 2014 (3 197 étudiants) ; **test** : cohortes 2015 à 2017 (1 227 étudiants) ;
- réglage par validation croisée par cohorte (log loss) : `C = 0,1` pour la régression logistique,
  largeur de bande 0,82 / 1,05 / 1,34 pour le noyau (T0 / T1 / T2) ;
- bornes de saisie et valeurs par défaut calculées sur le développement seulement (le test n'apprend rien au modèle) ;
- le script s'arrête si les modèles ne retrouvent pas, au dix-millième près, les ROC-AUC et Brier de l'évaluation finale.

| Sur le jeu de test (ROC-AUC) | T0 : inscription | T1 : fin du 1er semestre | T2 : fin du 2e semestre |
|---|---|---|---|
| Régression logistique (retenue) | 0,775 | 0,876 | 0,902 |
| Approche à noyau | 0,700 | 0,839 | 0,865 |

Le détail (intervalles de confiance, calibration, équité, limites) est dans le
[projet de recherche](https://github.com/onelngoma-source/abandon-universitaire).

## Identité visuelle

Palette : bleu `#3281E0`, bleu profond `#0D3863` (barre de navigation, bandeaux), jaune pâle `#F7FFBD` (onglet actif), fonds `#F4F6FA`. Titres en Space Grotesk, texte en Inter, les deux servis depuis
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
`SCORE (#etudiant_id, modele, probabilite, categorie, mode_calcul)`, clé primaire (etudiant_id, modele) ; `modele` vaut `logistique` ou `noyau`, `mode_calcul` vaut `T0`, `T1` ou `T2`.
Une base créée par la version du mémoire (modèles `rf`, modes `complet` / `precoce`) est reconstruite automatiquement au démarrage : elle ne contient que des données recalculables.
Le jeu de test et chaque fichier importé sont des cohortes : le tableau de bord affiche l'une ou l'autre.
`caracteristiques` conserve les valeurs fournies des 36 variables (JSON) : c'est ce qui permet de recalculer l'explication d'un étudiant à la demande.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

Ils vérifient :
- **la correspondance avec le projet de recherche** : découpage par cohorte (3 197 / 1 227 étudiants, 326 abandons au test),
  scores du tableau de bord identiques à l'évaluation finale, réglages identiques, aucune borne ni valeur par défaut issue du test ;
- **l'exactitude des explications** : la somme des contributions redonne exactement le logit de la régression logistique,
  et le calcul à la main sur les poids des étudiants redonne exactement la probabilité du noyau, aux trois moments ;
- l'identité tableau de bord / import (ordre des colonnes, séparateur, virgule décimale, correspondance manuelle),
  le choix du moment (T0, T1, T2), la saisie, la base, le mode démonstration et le rendu réel dans un navigateur.

## Ce que l'écran n'affiche volontairement pas

L'application s'adresse à des conseillers, pas à des statisticiens. Les détails de calcul sont absents de l'écran et
documentés dans le projet de recherche : formule du noyau et largeur de bande, contributions exactes de la régression
logistique, imputation des variables absentes, codage des 23 variables supplémentaires.

## Limites assumées

- **Données d'une seule université, au Portugal** : aucun résultat n'est établi pour un autre établissement sans nouvelle validation.
- **Calibration** : sur les cohortes 2015 à 2017, le taux d'abandon réel (26,6 %) est plus bas que celui du développement (34,3 %) ;
  le modèle surestime un peu le risque, surtout à l'inscription. Il faudrait le recalibrer chaque année sur la cohorte la plus récente.
- **Équité** : les abandons des étudiants boursiers sont sous-détectés (ils abandonnent rarement, donc leur risque estimé reste bas).
- **Variables financières** (débiteur, frais à jour) : leur date de mesure n'est pas documentée ; sans elles, la ROC-AUC à
  l'inscription passe de 0,775 à 0,733.
- Un fichier qui ne contient que les 13 champs du formulaire est calculé, mais 19 variables du modèle T2 sont alors estimées :
  le tableau n'est pas identique à celui des 36 variables (ROC-AUC 0,893 au lieu de 0,902 sur le jeu de test).
- Les 23 variables supplémentaires suivent le codage portugais du jeu d'origine.
- Compte administrateur unique, adapté à une démonstration ; à durcir avant tout usage réel.
