# Dispositif d'alerte précoce : risque d'abandon universitaire

Application de démonstration du projet « approche non paramétrique à noyau comparée au Machine Learning pour prédire
l'abandon universitaire », dans sa **version rigoureuse** : les modèles viennent du projet de recherche
[abandon-universitaire](https://github.com/onelngoma-source/abandon-universitaire) (découpage par cohorte, validation croisée
imbriquée, calibration vérifiée, seuil fixé par les coûts, test scellé ouvert une seule fois).
La version présentée lors de la soutenance est conservée dans l'historique Git (étiquette `version-soutenance`).

L'application est pensée pour le travail d'un **conseiller pédagogique** : savoir qui accompagner en priorité,
comprendre pourquoi, et savoir sur quoi agir. Elle affiche **un seul risque**, celui de la **régression logistique**
(modèle retenu, probabilités calibrées). L'**approche à noyau** de Nadaraya-Watson, sujet du mémoire, sert à montrer sur
chaque fiche les étudiants passés au profil le plus proche, et elle est comparée en détail dans la page « Fiabilité du modèle ».

Le modèle est choisi selon l'information disponible : **à l'inscription (T0)**, **à la fin du 1er semestre (T1)** ou
**à la fin du 2e semestre (T2)**. L'alerte se déclenche quand la probabilité atteint **1 sur 6** : un abandon non détecté
coûte autant que 5 accompagnements inutiles.

| Page | Adresse | Rôle |
|---|---|---|
| Suivi de cohorte | `/tableau` | Les étudiants classés du risque le plus élevé au plus faible. Un **curseur de capacité** (part des étudiants que l'équipe peut suivre) délimite la file d'accompagnement. Pour chacun : risque, niveau, facteur qui pèse le plus (en clair), signaux (dette, frais en retard, unités validées). À côté : alertes par filière, domaine sur lequel agir, et vérification si le devenir réel est connu |
| Fiche étudiant | `/etudiants/<id>` | Le risque et son niveau, son **évolution** de l'inscription à la fin du 2e semestre, ce qui l'augmente et ce qui le réduit (avec les **leviers d'action**), des pistes d'accompagnement, les 5 étudiants passés au profil le plus proche, le dossier ; navigation vers l'étudiant suivant de la file |
| Évaluer un étudiant | `/saisie` | Saisie guidée en trois étapes (inscription, 1er semestre, 2e semestre) ; le risque est recalculé à chaque modification |
| Importer une cohorte | `/import` | Un fichier CSV, une étape d'association des colonnes (36 variables, suggestions automatiques), puis le suivi de la cohorte |
| Fiabilité du modèle | `/fiabilite` | Évaluation sur les cohortes 2015 à 2017 recalculée au démarrage : ROC-AUC, Brier, part des abandons repérés selon la capacité, calibration, **équité par groupe**, comparaison des cinq modèles, limites |

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

1. Suivi de cohorte : les 1 227 étudiants des cohortes 2015 à 2017 sont déjà chargés. Régler la capacité à 20 % :
   la file contient 245 étudiants ; la carte « Cohorte au devenir connu » montre qu'elle contient 211 des 326 abandons réels.
2. Cliquer sur « Où se concentrent les alertes » pour filtrer une filière, puis ouvrir un étudiant.
3. Fiche : évolution du risque, facteurs en clair, pistes, étudiants au profil proche ; « Suivant dans la file ».
4. Évaluer un étudiant : exemple « En difficulté », puis décocher les semestres pour voir le risque à l'inscription.
5. Fiabilité du modèle : ROC-AUC 0,902, 86 % des abandons repérés au seuil, calibration, équité (boursiers), comparaison avec le noyau.
6. Importer une cohorte : « Fichier d'exemple », l'importer : le suivi obtenu est identique.

## Organisation du code

```
app.py                      création de l'application, enregistrement des volets
auth.py                     connexion (compte unique)
db.py                       base SQLite (sqlite3), schéma et requêtes
moteur/scoring.py           calcul unique : nettoyage, choix du moment, valeurs absentes, modèles, explications, trajectoire
moteur/langage.py           traduction des variables en langage clair, domaine et levier d'action
moteur/fiabilite.py         évaluation sur les cohortes de test (calibration, capacité, équité)
moteur/variables.py         variables par moment, copie conforme du projet de recherche
moteur/noyau.py             estimateur de Nadaraya-Watson
moteur/cohortes.py          construction d'une cohorte (jeu de test ou fichier) : une seule fonction, `importer`
moteur/conseils.py          pistes d'accompagnement, tirées des leviers
volets/                     un module par page (tableau, fiche, saisie, import_csv, fiabilite) + api_cohortes
templates/, static/         gabarits, une feuille de style, Chart.js et les polices en local : aucune dépendance externe
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

Bleu nuit `#0D3863` et or `#D8B85C` pour l'identité ; titres en Space Grotesk, texte en Inter, servis depuis
`static/vendor/fonts/` (aucun appel réseau). Le vert, l'orange et le rouge sont réservés aux niveaux de risque :
ce sont les seules couleurs porteuses de sens. Tous les effets respectent `prefers-reduced-motion`.

## Changer l'image de fond de la page de connexion

Déposez une image nommée `connexion.jpg` (ou `.png`, `.webp`, `.avif`) dans `static/fonds/`, puis rechargez la page :
elle est prise en compte aussitôt, sans toucher au code. Retirez le fichier pour revenir au dégradé bleu.
L'image s'affiche telle quelle : rien n'est écrit directement dessus, le texte vivant dans la carte et dans le volet bleu.
Deux réglages facultatifs : `FOND_CONNEXION` désigne un autre fichier du dossier (ou une adresse `https://`),
et `FOND_VOILE` assombrit l'image de 0 à 90 (0 par défaut, à monter si une image claire noie la carte). Le détail est rappelé dans
`static/fonds/LISEZ-MOI.txt`.

## Modèle de données (SQLite)

`COHORTE (id, nom, origine, fichier, effectif, ignorees, proprietaire, date_creation)` 1-n
`ETUDIANT (id, #cohorte_id, reference, filiere, genre, age, boursier, debiteur, frais_a_jour, note_s1, note_s2, inscrites_s1, validees_s1, inscrites_s2, validees_s2, facteur, domaine_facteur, devenir_reel, abandon_reel, caracteristiques)` 1-2
`SCORE (#etudiant_id, modele, probabilite, categorie, mode_calcul)`, clé primaire (etudiant_id, modele) ; `modele` vaut `logistique` ou `noyau`, `mode_calcul` vaut `T0`, `T1` ou `T2`.
Une base créée par une version précédente est reconstruite automatiquement au démarrage : elle ne contient que des données recalculables.
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
- l'identité jeu de test chargé / fichier importé (ordre des colonnes, séparateur, virgule décimale, correspondance manuelle),
  le choix du moment (T0, T1, T2), la saisie, la base, le mode démonstration ;
- le parcours réel dans un navigateur : file classée par risque, capacité, filtres, fiche et étudiant suivant, saisie en direct, page de fiabilité.

## Ce que l'écran n'affiche volontairement pas

L'application s'adresse à des conseillers, pas à des statisticiens. Les facteurs sont traduits en phrases
(« 2 unités validées sur 6 au 1er semestre ») avec une intensité (fort, modéré, léger) plutôt qu'en logits. Les détails de
calcul sont documentés dans le projet de recherche : formule du noyau et largeur de bande, contributions exactes de la
régression logistique, imputation des variables absentes, codage des 23 variables supplémentaires.

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
