# Alerte précoce : outil de repérage et de suivi du risque d'abandon universitaire

Outil opérationnel issu du projet « approche non paramétrique à noyau comparée au Machine Learning pour prédire
l'abandon universitaire ». Les modèles viennent du projet de recherche
[abandon-universitaire](https://github.com/onelngoma-source/abandon-universitaire) (découpage par cohorte, validation
croisée imbriquée, calibration vérifiée, seuil fixé par les coûts, test scellé ouvert une seule fois).
La version présentée lors de la soutenance est conservée dans l'historique Git (étiquette `version-soutenance`).

**Pour un établissement qui veut l'utiliser : lire d'abord [GUIDE_MISE_EN_SERVICE.md](GUIDE_MISE_EN_SERVICE.md)**
(organisation, cadre légal au Gabon, installation, calendrier annuel, validation du modèle sur l'établissement,
mention d'information et charte d'usage).

## Le principe

1. **Repérer.** Chaque étudiant reçoit une probabilité d'abandon, estimée par la régression logistique (modèle
   retenu, probabilités calibrées) avec l'information disponible : **à l'inscription (T0)**, **à la fin du 1er semestre
   (T1)**, **à la fin du 2e semestre (T2)**. Les promotions sont importées à la rentrée, puis mises à jour à chaque
   semestre : un étudiant garde son historique d'estimations.
2. **Alerter.** Dès que le risque atteint **1 sur 6** (un abandon manqué coûte autant que 5 accompagnements inutiles),
   un **dossier de suivi** s'ouvre, avec une échéance. Un dossier ouvert dont le risque monte de 10 points est signalé
   « en hausse ». Un dossier clos ne se rouvre que si le risque monte encore.
3. **Accompagner.** Le dossier passe par *à contacter → contacté → entretien réalisé → accompagnement en cours → clos*
   (avec un motif). Chaque étape fixe la prochaine échéance ; chaque action (appel, entretien, tutorat, service
   financier…) est consignée avec son auteur. La fiche explique le risque en clair et propose des pistes.
4. **Piloter.** Dossiers non attribués, retards, délai avant premier contact, charge par conseiller, actions menées,
   motifs de clôture, et en fin d'année le devenir des étudiants suivis.
5. **Vérifier.** Quand le devenir réel est connu, l'outil recalcule sa fiabilité sur l'établissement et signale tout
   écart avec la référence ; `scripts/recalibrer.py` corrige le niveau des probabilités si besoin.

L'approche à noyau de Nadaraya-Watson, sujet du mémoire, montre sur chaque fiche les étudiants passés au profil le
plus proche ; elle est comparée aux autres modèles dans la page « Fiabilité du modèle ».

## Rôles et pages

| Page | Conseiller | Responsable | Administrateur |
|---|---|---|---|
| Dossiers (`/dossiers`) : mes dossiers, non attribués, en retard, en hausse, clos ; export | ses dossiers et les non attribués | tous, attribution groupée | tous |
| Suivi de cohorte (`/tableau`) : promotion classée par risque, capacité d'accompagnement ; export de la file | oui | oui | oui, et suppression |
| Fiche étudiant (`/etudiants/<id>`) : dossier, journal, risque, évolution, facteurs, pistes, profils proches, historique, mise à jour des résultats | oui | oui, et devenir réel, référent | idem |
| Simuler un dossier (`/saisie`) : estimation sans enregistrement | oui | oui | oui |
| Importer (`/import`) : nouvelle promotion ou mise à jour par matricule | non | oui | oui |
| Pilotage (`/pilotage`) | non | oui | oui |
| Fiabilité du modèle (`/fiabilite`) : référence, calibration, équité, comparaison, surveillance | oui | oui | oui |
| Comptes, Journal d'activité, Données et conservation (`/admin/...`) | non | non | oui |

## Lancer l'application

```bash
pip install -r requirements.txt
MODE_DEMO=1 python app.py          # démonstration : http://localhost:5000, comptes admin / responsable / conseiller1 / conseiller2, mot de passe « demo »
python app.py                      # établissement : base vide, compte admin / changez-moi (à changer à la première connexion)
# production : DATABASE_URL=postgresql://... gunicorn -w 2 --threads 4 -b 0.0.0.0:$PORT app:app
```

Toutes les variables d'environnement (base, sécurité, délais, conservation, courriels) sont décrites dans le
[guide de mise en service](GUIDE_MISE_EN_SERVICE.md#variables-denvironnement). En mode démonstration, le suivi est déjà
engagé sur les cohortes 2015 à 2017 (comptes et actions fictifs) et rien de destructeur n'est permis.

## Scénario de démonstration (5 minutes)

1. Connexion en **conseiller1** : « Dossiers » s'ouvre sur ses alertes, retards en tête. Ouvrir un dossier : le journal,
   « Marquer comme contacté », consigner un entretien, clore avec un motif.
2. Connexion en **responsable** : « Pilotage » (195 dossiers non attribués, délai avant premier contact, charge), puis
   « Dossiers » → *Non attribués* : sélectionner, attribuer en une fois.
3. « Suivi de cohorte » : curseur de capacité à 20 % ; la carte « devenir connu » montre que la file contient 211 des
   326 abandons réels.
4. « Fiabilité du modèle » : ROC-AUC 0,902, calibration, équité (boursiers), comparaison avec le noyau, surveillance.
5. Connexion en **admin** : « Comptes », « Journal » (chaque consultation de fiche y figure), « Données ».

## Organisation du code

```
app.py                      création de l'application, sécurité (en-têtes), enregistrement des volets
auth.py                     comptes, rôles, mots de passe, verrouillage, CSRF, compte de l'utilisateur
db.py                       base (SQLAlchemy Core) : SQLite par défaut, PostgreSQL avec DATABASE_URL
moteur/                     calcul : scoring.py (modèles, explications, trajectoire, recalibration), langage.py,
                            fiabilite.py (évaluation de référence), variables.py, noyau.py, cohortes.py (lecture des fichiers)
metier/                     règles de l'outil : evaluations.py (enregistrement, règle d'alerte), dossiers.py (suivi),
                            pilotage.py, surveillance.py, journal.py, regles.py (statuts, délais), demo.py
volets/                     une page par module : dossiers, tableau, fiche, saisie, import_csv, pilotage, fiabilite,
                            administration, api_cohortes
templates/, static/         gabarits, une feuille de style, Chart.js et les polices en local
outils/rappels.py           rappels quotidiens par courriel (tâche planifiée)
scripts/entrainer_modeles.py  entraîne les modèles et vérifie qu'ils retrouvent l'évaluation finale
scripts/recalibrer.py       recalibration sur les promotions passées de l'établissement
data/                       jeu de données UCI, jeu de test (cohortes 2015 à 2017)
models/modeles.joblib       les six modèles (deux par moment), bornes et valeurs par défaut
tests/                      tests pytest (SQLite, ou PostgreSQL avec TEST_DATABASE_URL)
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
`static/vendor/fonts/` (aucun appel réseau). Le vert, l'orange et le rouge sont réservés aux niveaux de risque ;
chaque statut de dossier a sa couleur. Tous les effets respectent `prefers-reduced-motion`.

## Changer l'image de fond de la page de connexion

Déposez une image nommée `connexion.jpg` (ou `.png`, `.webp`, `.avif`) dans `static/fonds/`, puis rechargez la page :
elle est prise en compte aussitôt, sans toucher au code. Retirez le fichier pour revenir au dégradé bleu.
L'image s'affiche telle quelle : rien n'est écrit directement dessus, le texte vivant dans la carte et dans le volet bleu.
Deux réglages facultatifs : `FOND_CONNEXION` désigne un autre fichier du dossier (ou une adresse `https://`),
et `FOND_VOILE` assombrit l'image de 0 à 90 (0 par défaut, à monter si une image claire noie la carte). Le détail est rappelé dans
`static/fonds/LISEZ-MOI.txt`.

## Modèle de données

`UTILISATEUR (id, identifiant, nom, email, role, mdp_hache, actif, doit_changer_mdp, cree_le, derniere_connexion)`
`PROMOTION (id, nom, origine, cree_le)` 1-n `ETUDIANT (id, #promotion_id, matricule, nom, email, telephone, …, caracteristiques, #referent_id, dernière estimation, devenir_reel)`, matricule unique dans sa promotion
`ETUDIANT` 1-n `EVALUATION (id, #etudiant_id, #lot_id, #utilisateur_id, moment, probabilite, probabilite_noyau, categorie, facteur, caracteristiques, modele_version, cree_le)`
`PROMOTION` 1-n `LOT (id, fichier, effectif, nouveaux, mis_a_jour, ignorees, alertes_ouvertes, #utilisateur_id, cree_le)` : un import
`ETUDIANT` 1-n `DOSSIER (id, statut, #conseiller_id, echeance, ouvert_le, ouvert_par, probabilite_ouverture, relance, premier_contact_le, clos_le, motif_cloture, probabilite_cloture)` 1-n `ACTION (type, texte, statut_avant, statut_apres, #utilisateur_id, cree_le)`
`JOURNAL (utilisateur, action, objet, objet_id, detail, adresse, cree_le)`

Contraintes en base : rôle, statut, moment et catégorie dans leurs listes ; un dossier clos a toujours un motif ;
suppression en cascade d'une promotion. Toutes les dates sont en UTC.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests
```

Ils vérifient :
- **la correspondance avec le projet de recherche** : découpage par cohorte (3 197 / 1 227 étudiants, 326 abandons au test),
  scores identiques à l'évaluation finale, réglages identiques, aucune borne ni valeur par défaut issue du test ;
- **l'exactitude des explications** : la somme des contributions redonne exactement le logit de la régression logistique,
  et le calcul à la main sur les poids des étudiants redonne exactement la probabilité du noyau, aux trois moments ;
- **le suivi** : un dossier par alerte et un seul, mise à jour par matricule, parcours complet d'un dossier, hausse du
  risque, non-réouverture après clôture, rappels par courriel, recalibration ;
- **les droits et la sécurité** : rôles, dossier d'un autre conseiller, jeton CSRF, verrouillage, mot de passe, dernier
  administrateur, compte désactivé, journal, mode démonstration ;
- l'import (ordre des colonnes, séparateur, virgule décimale, correspondance manuelle) et le parcours réel dans un
  navigateur (file, fiche, traitement d'une alerte, pilotage, administration).

La même suite passe sur PostgreSQL : `TEST_DATABASE_URL=postgresql://... python -m pytest tests`.

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
