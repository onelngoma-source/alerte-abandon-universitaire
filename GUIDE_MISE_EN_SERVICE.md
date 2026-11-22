# Guide de mise en service dans un établissement

Ce guide s'adresse à l'établissement qui veut utiliser l'outil d'alerte précoce pour de vrai : la direction des
études, le service de scolarité, le service informatique et la personne chargée de la protection des données.
Il complète le README, qui décrit le fonctionnement technique.

L'outil est prêt à être installé. Il n'est **pas** prêt à décider seul de quoi que ce soit, et il ne doit jamais le
faire : il signale des étudiants à qui proposer un accompagnement, des conseillers les rencontrent, et ce sont eux qui
jugent.

---

## 1. Ce que l'outil fait, et ce qu'il ne fait pas

| L'outil fait | L'outil ne fait pas |
|---|---|
| estimer, pour chaque étudiant, la probabilité d'abandonner avant la fin du cursus, à l'inscription puis à la fin de chaque semestre | prendre une décision sur un étudiant (orientation, bourse, sanction, refus d'inscription) |
| ouvrir un dossier de suivi quand le risque atteint 1 sur 6, avec une échéance | contacter l'étudiant à la place du conseiller |
| montrer ce qui fait monter ou baisser le risque, en langage clair | établir une cause : le modèle repère des associations |
| suivre le travail des conseillers : statuts, actions, délais, charge | garantir que l'accompagnement réduit l'abandon (voir la section 8) |
| vérifier chaque année sa propre fiabilité sur l'établissement | rester fiable sans être vérifié : un établissement ne ressemble pas forcément aux données d'apprentissage |

---

## 2. Avant d'installer : quatre décisions à prendre

**Qui reçoit les alertes ?** Il faut au moins un conseiller nommé, avec du temps réservé. Sur les cohortes de test,
37 % des étudiants passent le seuil à la fin du 2e semestre, et 67 % à l'inscription. Une équipe qui ne peut en
accompagner que 20 % doit s'appuyer sur la page « Suivi de cohorte » (curseur de capacité) et traiter d'abord les
risques les plus élevés.

**Quels délais ?** Par défaut : premier contact sous 7 jours, entretien sous 14 jours après le contact, point de suivi
tous les 30 jours. Ils se changent par variables d'environnement (section 4).

**Combien de temps garder les données ?** Par défaut 3 ans après la dernière mise à jour d'une promotion
(`DUREE_CONSERVATION_ANNEES`). La durée retenue doit figurer dans l'information donnée aux étudiants.

**Qui administre ?** Un administrateur (comptes, imports, purge), au moins un responsable (attribution, pilotage).
Jamais de compte partagé : le journal d'activité n'a de valeur que si chaque compte correspond à une personne.

---

## 3. Le cadre légal au Gabon

> Cette section résume des obligations générales. Elle ne remplace pas l'avis d'un juriste ni celui de l'Autorité.

La protection des données personnelles relève de la **loi n° 001/2011 du 25 septembre 2011**, modifiée par la
**loi n° 025/2023 du 12 juillet 2023**, qui a fait de l'ancienne CNPDCP l'**Autorité pour la protection des données à
caractère personnel et de la vie privée (APDPVP)**. Points qui concernent directement l'outil (numéros d'articles de
la loi modifiée) :

- **Formalité préalable.** Un traitement automatisé est en principe **déclaré** à l'APDPVP avant sa mise en œuvre
  (art. 78 et 79) ; certains traitements sensibles demandent une **autorisation** (art. 81), et les traitements d'un
  établissement public peuvent relever d'un acte réglementaire (art. 82 et 83). Faire qualifier le traitement par
  l'APDPVP ou par le délégué à la protection des données, s'il y en a un (art. 89).
- **Information des étudiants** au moment de la collecte : finalité, destinataires, durée de conservation, droits
  (art. 98). Un modèle de mention est proposé en annexe A.
- **Droits** d'accès (art. 43 et 44), de rectification et d'effacement (art. 50 et suivants), d'opposition (art. 61).
  La fiche d'un étudiant regroupe tout ce que l'outil sait de lui : c'est la base d'une réponse à une demande d'accès.
- **Décision automatisée.** Une personne peut s'opposer à une décision fondée exclusivement sur un traitement
  automatisé qui l'affecte de façon importante, et une intervention humaine doit être prévue (art. 66 à 68).
  L'outil est conçu pour qu'**aucune décision ne soit automatique** : il ouvre un dossier, un conseiller juge. La
  charte (annexe B) l'écrit noir sur blanc.
- **Conservation limitée** à la durée nécessaire (art. 70) : page « Données », purge des promotions échues.
- **Sécurité** des données et notification des violations (art. 79 et 87) : section 5.

Variables à manier avec un soin particulier : l'outil utilise le genre, l'âge, la situation financière (bourse, dette,
frais) et des informations familiales (diplôme et profession des parents). Elles servent au calcul, mais une alerte
ne doit jamais conduire à traiter un étudiant différemment pour ces motifs. La page « Fiabilité » vérifie que l'outil
détecte aussi bien dans chaque groupe ; ce n'est pas le cas pour les boursiers, et la fiche le rappelle.

---

## 4. Installation en production

### Base de données

En production, utilisez **PostgreSQL** (sauvegardes, accès concurrents). SQLite convient pour un essai ou une
démonstration. L'application crée elle-même ses tables au premier démarrage.

### Variables d'environnement

| Variable | Valeur en production | Rôle |
|---|---|---|
| `DATABASE_URL` | `postgresql://utilisateur:motdepasse@hote:5432/alerte` | base PostgreSQL |
| `FLASK_SECRET_KEY` | 64 caractères aléatoires (`python -c "import secrets; print(secrets.token_hex(32))"`) | signature des sessions ; à garder secrète et stable |
| `ADMIN_IDENTIFIANT` | identifiant du premier administrateur | créé au premier démarrage seulement |
| `ADMIN_MDP_HACHE` | empreinte du mot de passe (`python -c "from werkzeug.security import generate_password_hash as g; print(g('...'))"`) | sans elle : « changez-moi », à changer à la première connexion |
| `MODE_DEMO` | `0` | **obligatoire** : sinon, comptes fictifs et données de test |
| `DEMO_PRELOAD` | `0` | ne pas charger les étudiants de test |
| `COOKIE_SECURISE` | `1` | cookies envoyés seulement en HTTPS |
| `DUREE_SESSION_HEURES` | `8` | déconnexion automatique |
| `DUREE_CONSERVATION_ANNEES` | `3` (ou la durée déclarée) | conservation des données |
| `DELAI_PREMIER_CONTACT_JOURS`, `DELAI_ENTRETIEN_JOURS`, `DELAI_POINT_SUIVI_JOURS` | `7`, `14`, `30` | échéances automatiques |
| `SMTP_HOTE`, `SMTP_PORT`, `SMTP_UTILISATEUR`, `SMTP_MDP`, `SMTP_EXPEDITEUR`, `URL_APPLICATION` | selon la messagerie de l'établissement | rappels quotidiens (section 6) |

### Démarrage

```bash
pip install -r requirements.txt
gunicorn -w 2 --threads 4 --timeout 120 -b 0.0.0.0:8000 app:app
```

Placez l'application derrière un serveur HTTPS (nginx, Caddy, ou l'hébergeur). Ne l'exposez jamais en HTTP simple :
les fiches contiennent des données personnelles.

### Premier démarrage

1. Connectez-vous avec le compte administrateur, changez son mot de passe (imposé).
2. « Comptes » : créez un compte par conseiller et par responsable, avec leur courriel. Chaque création affiche un
   mot de passe provisoire, à transmettre de vive voix ; il est changé à la première connexion.
3. « Données » : vérifiez que la base indiquée est PostgreSQL et que le mode est « Établissement ».

---

## 5. Sécurité : ce qui est en place, ce qui reste à faire

**En place dans l'application.** Comptes nominatifs et trois rôles ; mots de passe hachés, 10 caractères au moins,
changement imposé à la première connexion ; verrouillage après 5 échecs de connexion depuis une même adresse ;
jeton anti-CSRF sur toute modification ; cookies `HttpOnly`, `SameSite`, `Secure` (avec `COOKIE_SECURISE=1`) ;
session de 8 heures ; un compte désactivé perd sa session immédiatement ; journal de toutes les connexions,
consultations de fiches, imports, exports et modifications ; les courriels de rappel ne contiennent que le matricule
et l'échéance.

**À la charge de l'établissement.**

- sauvegarde quotidienne chiffrée de la base (`pg_dump`), conservée hors du serveur, et un essai de restauration par
  trimestre ;
- HTTPS, pare-feu, mises à jour du système et de PostgreSQL ;
- revue des comptes à chaque départ d'un agent (désactiver, ne pas supprimer : le journal reste lisible) ;
- consultation du journal en cas de doute, et procédure de notification en cas de violation de données ;
- les fichiers exportés (CSV) sont des données personnelles : ne pas les envoyer par messagerie personnelle, les
  supprimer après usage.

---

## 6. L'année avec l'outil

| Quand | Qui | Quoi |
|---|---|---|
| Rentrée | administrateur ou responsable | « Importer » → *Nouvelle promotion* : le fichier des inscrits (matricule, nom, contact, informations d'inscription). Le risque est estimé « à l'inscription » ; les dossiers s'ouvrent pour les alertes. |
| Chaque matin | conseillers | « Dossiers » → *Mes dossiers* : les retards et les risques en hausse sont en tête. Contacter, consigner, avancer le statut. |
| Chaque semaine | responsable | « Pilotage » : dossiers non attribués (les répartir), retards, délai avant premier contact, charge de chacun. |
| Fin du 1er semestre | responsable | « Importer » → *Mettre à jour* la promotion avec les résultats du semestre. Les mêmes étudiants (même matricule) sont réévalués ; un risque qui monte de 10 points signale le dossier « en hausse » ; de nouveaux dossiers s'ouvrent. |
| Fin du 2e semestre | responsable | idem avec les résultats du 2e semestre. |
| Fin d'année | responsable | renseigner le **devenir réel** (fichier avec une colonne « devenir » : abandon, diplômé, inscrit ; ou sur chaque fiche). |
| Juillet | direction, référent données | « Fiabilité du modèle » → *Sur votre établissement* : le modèle tient-il ? Sinon, section 7. « Pilotage » → *En fin d'année*. « Données » : purge des promotions échues. |

**Rappels par courriel.** Programmez chaque jour ouvré, par exemple à 7 h :

```bash
python -m outils.rappels            # envoie
python -m outils.rappels --essai    # montre sans envoyer
```

(tâche cron du serveur, ou « Cron Job » chez l'hébergeur, avec les mêmes variables d'environnement que l'application).

---

## 7. Valider le modèle sur l'établissement avant de s'y fier

Le modèle a appris sur une université portugaise (cohortes 2008 à 2014) et a été évalué sur les cohortes suivantes
de la même université. **Rien ne garantit qu'il soit aussi bon ailleurs.** Avant un usage réel :

**Étape 1, rétrospective (recommandée, avant la première rentrée).** Rassemblez une ou deux promotions passées dont
on connaît le devenir, dans le format d'import, avec une colonne « devenir ». Importez-les dans une promotion nommée
par exemple « Validation 2023-2024 ». La page « Fiabilité » → *Sur votre établissement* affiche alors, pour chaque
moment, la ROC-AUC comparée à la référence, le risque moyen annoncé et le taux d'abandon observé.

Critères proposés pour une mise en service :

| Indicateur | Seuil |
|---|---|
| ROC-AUC à la fin du 1er semestre | ≥ 0,75 |
| écart entre risque moyen annoncé et taux d'abandon observé | ≤ 5 points (sinon : recalibrer) |
| part des abandons repérés au seuil d'alerte | ≥ 70 % |

**Étape 2, recalibration si les probabilités sont décalées.** Si le classement est bon mais que le niveau du risque
est décalé (taux d'abandon local différent), ajustez une correction sur les promotions passées :

```bash
python scripts/recalibrer.py promotions_passees.csv           # diagnostic seul
python scripts/recalibrer.py promotions_passees.csv --ecrire  # écrit models/recalibration.joblib
```

La correction n'est retenue, moment par moment, que si elle améliore le score de Brier en validation croisée ; elle
ne change jamais l'ordre des étudiants. Redémarrez l'application : la version du modèle affichée (pages « Fiabilité »
et « Données », et chaque estimation enregistrée) mentionne la recalibration.

**Étape 3, si le classement lui-même est mauvais** (ROC-AUC nettement sous la référence). La recalibration ne suffit
pas : il faut réentraîner le modèle sur les données de l'établissement, avec le protocole du projet de recherche
([abandon-universitaire](https://github.com/onelngoma-source/abandon-universitaire) : découpage par cohorte, validation
croisée imbriquée, test scellé), puis `scripts/entrainer_modeles.py`. Comptez au moins trois promotions au devenir
connu.

**Étape 4, première année en accompagnement prudent.** La première année, présentez les alertes comme des signaux à
vérifier, et refaites l'étape 1 en juillet sur la promotion de l'année.

---

## 8. Mesurer l'effet de l'accompagnement (si on veut aller plus loin)

La page « Pilotage » compare le taux d'abandon des étudiants alertés qui ont eu un entretien et de ceux qui n'en ont
pas eu. **Ce n'est pas une mesure d'effet** : les étudiants joignables et volontaires ne sont pas comparables aux
autres. Pour mesurer réellement l'effet du dispositif, il faut un protocole d'évaluation décidé à l'avance (par
exemple, comparer des promotions avant et après la mise en service à risque égal, ou un déploiement progressif par
filière), avec l'accord de l'établissement et dans le respect de l'égalité de traitement.

---

## Annexe A. Modèle de mention d'information aux étudiants

> **Accompagnement de la réussite.** Pour proposer un accompagnement aux étudiants qui pourraient rencontrer des
> difficultés, [l'établissement] utilise un outil d'aide qui estime, à partir de votre dossier d'inscription et de
> vos résultats semestriels, un niveau de risque d'interruption des études. Cette estimation sert uniquement à vous
> proposer un échange avec un conseiller. **Aucune décision vous concernant n'est prise par l'outil**, et l'estimation
> n'est transmise ni aux enseignants ni à des tiers.
>
> Responsable du traitement : [nom, adresse]. Données utilisées : informations d'inscription, situation de bourse et
> de paiement des frais, résultats semestriels. Accès : conseillers et responsables de l'accompagnement, nommément
> désignés. Durée de conservation : [3] ans après la fin de l'année universitaire.
>
> Vous pouvez accéder à ces données, les faire rectifier, vous opposer à leur traitement ou demander qu'un conseiller
> réexamine votre situation, auprès de [contact]. Vous pouvez saisir l'Autorité pour la protection des données à
> caractère personnel et de la vie privée (APDPVP). Traitement déclaré sous le n° [numéro de récépissé].

## Annexe B. Charte d'usage (à signer par chaque utilisateur)

1. Une alerte sert à **proposer** un accompagnement. Elle ne justifie aucune décision défavorable : orientation
   imposée, refus, sanction, mention au dossier, information des enseignants.
2. Le risque est une **estimation**, souvent fausse au cas par cas. L'entretien prime toujours sur le chiffre.
3. Je ne consulte que les fiches des étudiants que je suis, ou dont la consultation est nécessaire à ma mission.
   Mes consultations sont journalisées.
4. Je ne communique ni mon mot de passe ni les données de l'outil. Je n'exporte que ce qui est nécessaire et je
   supprime les exports après usage.
5. Je n'interprète jamais le genre, l'âge, la situation familiale ou financière d'un étudiant comme un jugement sur
   lui.
6. Je consigne dans le dossier ce qui est utile au suivi, avec des faits et sans appréciation sur la personne.
7. Je signale à l'administrateur tout usage anormal ou toute perte de données.

## Annexe C. Liste de contrôle avant la mise en service

- [ ] Déclaration (ou demande d'autorisation) déposée auprès de l'APDPVP ; récépissé reçu
- [ ] Mention d'information publiée (règlement des études, espace numérique, dossier d'inscription)
- [ ] Charte signée par chaque utilisateur
- [ ] PostgreSQL, HTTPS, `MODE_DEMO=0`, `COOKIE_SECURISE=1`, `FLASK_SECRET_KEY` stable
- [ ] Sauvegarde quotidienne en place et restauration testée
- [ ] Un compte par personne ; mot de passe administrateur changé
- [ ] Validation rétrospective faite (section 7) ; recalibration si nécessaire
- [ ] Rappels par courriel programmés et testés (`--essai`)
- [ ] Délais et durée de conservation fixés et cohérents avec la déclaration
