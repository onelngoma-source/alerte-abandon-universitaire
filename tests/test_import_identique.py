"""Le volet 3 (import CSV) doit produire exactement le tableau du volet 1 (tableau de bord)."""
import io
import json

import pandas as pd

from conftest import RACINE, lignes_sans_id, televerser


def test_import_du_jeu_de_test_identique_au_tableau_de_bord(client, contenu_jeu_de_test):
    id_tableau = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    r = televerser(client, contenu_jeu_de_test, "jeu_de_test_1328.csv")
    assert r.status_code == 200 and r.json["nb_ignorees"] == 0 and r.json["effectif"] == 1328
    lignes_t, d_t = lignes_sans_id(client, id_tableau)
    lignes_i, d_i = lignes_sans_id(client, r.json["cohorte_id"])
    assert lignes_t == lignes_i                      # meme tableau, ligne par ligne, valeur par valeur
    assert d_t["metriques"] == d_i["metriques"]      # memes indicateurs
    assert d_t["memoire"] == d_i["memoire"] is not None  # la concordance avec le memoire s'affiche aussi


def test_ordre_des_colonnes_separateur_et_virgule_decimale_sans_effet(client, contenu_jeu_de_test):
    reference = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str)
    df = df[list(reversed(df.columns))]                     # colonnes dans l'ordre inverse
    texte = df.to_csv(index=False, sep=";")
    # virgule decimale (fichier issu d'un tableur francais)
    texte = "\n".join(l if i == 0 else l.replace(".", ",") for i, l in enumerate(texte.splitlines()))
    r = televerser(client, texte.encode("utf-8"), "tableur_fr.csv")
    assert r.status_code == 200 and r.json["nb_ignorees"] == 0
    assert lignes_sans_id(client, reference)[0] == lignes_sans_id(client, r.json["cohorte_id"])[0]


def test_correspondance_manuelle_des_colonnes_donne_le_meme_tableau(client, contenu_jeu_de_test):
    """En-tetes renommes (francais) puis re-associes par l'etape de correspondance : meme resultat."""
    reference = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str)
    from moteur.referentiels import CHAMPS_FORMULAIRE, LIBELLES_CHAMPS
    renommage = {c: "Mon " + LIBELLES_CHAMPS[c] for c in CHAMPS_FORMULAIRE}
    renommage["Reference"] = "Matricule"
    renommage["Target"] = "Statut final"
    fichier = df.rename(columns=renommage).to_csv(index=False).encode("utf-8")
    correspondance = {c: renommage[c] for c in CHAMPS_FORMULAIRE}
    correspondance.update({"reference": "Matricule", "devenir": "Statut final"})
    analyse = client.post("/api/analyser-fichier", data={"fichier": (io.BytesIO(fichier), "x.csv")},
                          content_type="multipart/form-data").json
    assert analyse["mapping_necessaire"] is True
    r = televerser(client, fichier, "renomme.csv", mapping=json.dumps(correspondance))
    assert r.status_code == 200 and r.json["nb_ignorees"] == 0
    assert lignes_sans_id(client, reference)[0] == lignes_sans_id(client, r.json["cohorte_id"])[0]


def test_fichier_reduit_aux_13_champs_est_calcule_avec_estimation(client, contenu_jeu_de_test):
    """Avec les seuls 13 champs, les 23 autres variables sont estimees : le tableau existe mais
    n'est PAS identique (c'est attendu et affiche), et reste de bonne qualite."""
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str)
    from moteur.referentiels import CHAMPS_FORMULAIRE
    fichier = df[["Reference"] + CHAMPS_FORMULAIRE + ["Target"]].to_csv(index=False).encode("utf-8")
    r = televerser(client, fichier, "reduit.csv")
    assert r.status_code == 200 and r.json["variables_reconnues"] == 13 and r.json["moyenne_estimees"] == 23.0
    d = client.get(f"/api/cohortes/{r.json['cohorte_id']}").json
    assert len(d["lignes"]) == 1328
    assert d["memoire"] is not None  # meme references : la comparaison au memoire est montree, l'ecart se lit
    assert d["metriques"]["ml"]["auc"] > 0.88 and d["metriques"]["noyau"]["auc"] > 0.83
    # le test d'identite est discriminant : ici les probabilites different bien du tableau de bord
    reference = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    p_ref = [l["p_ml"] for l in client.get(f"/api/cohortes/{reference}").json["lignes"]]
    assert p_ref != [l["p_ml"] for l in d["lignes"]]


def test_fichier_sans_deuxieme_semestre_passe_en_mode_precoce(client, contenu_jeu_de_test):
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str)
    from moteur.referentiels import CHAMPS_FORMULAIRE
    colonnes = ["Reference"] + [c for c in CHAMPS_FORMULAIRE if "2nd sem" not in c]
    r = televerser(client, df[colonnes].head(40).to_csv(index=False).encode("utf-8"), "precoce.csv")
    assert r.status_code == 200 and r.json["nb_precoces"] == 40
    assert {l["mode"] for l in client.get(f"/api/cohortes/{r.json['cohorte_id']}").json["lignes"]} == {"precoce"}


def test_lignes_invalides_ignorees_et_signalees(client):
    contenu = ("Curricular units 1st sem (enrolled),Curricular units 1st sem (approved),Curricular units 1st sem (grade),"
               "Curricular units 2nd sem (grade),Debtor,Scholarship holder,Age at enrollment,Course\n"
               "6,5,13.5,12,0,1,19,9500\n6,4,abc,12,0,1,22,9500\n5,3,10,9,1,0,30,9119\n").encode()
    r = televerser(client, contenu)
    assert r.status_code == 200 and r.json["effectif"] == 2 and r.json["nb_ignorees"] == 1
    assert r.json["lignes_ignorees"][0]["ligne"] == 3  # numero de ligne dans le fichier, en-tete compris


def test_fichier_non_reconnu_refuse_avec_message(client):
    r = televerser(client, b"a;b;c\n1;2;3\n")
    assert r.status_code == 400 and "non reconnue" in r.json["erreur"]


def test_anciens_fichiers_d_essai_de_l_application(client):
    """Les deux fichiers d'essai du volet import d'origine restent acceptes."""
    r = televerser(client, (RACINE / "tests/fixtures/import_13_champs.csv").read_bytes(), "t1.csv")
    assert r.status_code == 200 and r.json["effectif"] > 0
    contenu = (RACINE / "tests/fixtures/import_colonnes_differentes.csv").read_bytes()
    analyse = client.post("/api/analyser-fichier", data={"fichier": (io.BytesIO(contenu), "t2.csv")},
                          content_type="multipart/form-data").json
    assert analyse["mapping_necessaire"] is True
    correspondance = {"reference": "Nom_Etudiant", "Curricular units 1st sem (grade)": "Note_Semestre_1",
                      "Curricular units 2nd sem (grade)": "Note_Semestre_2",
                      "Curricular units 1st sem (approved)": "Matieres_Validees_S1",
                      "Curricular units 2nd sem (approved)": "Matieres_Validees_S2",
                      "Scholarship holder": "A_Une_Bourse", "Debtor": "Est_Endette", "Age at enrollment": "Age",
                      "Course": "Filiere_Etudiant"}
    r = televerser(client, contenu, "t2.csv", mapping=json.dumps(correspondance))
    assert r.status_code == 200 and r.json["effectif"] == 20 and r.json["nb_ignorees"] == 0
    lignes = client.get(f"/api/cohortes/{r.json['cohorte_id']}").json["lignes"]
    assert lignes[0]["reference"] == "Ndong_1" and lignes[0]["filiere"] == "Sante" and lignes[0]["boursier"] == 1


def _fichier_renomme(contenu_jeu_de_test, moteur):
    """Le jeu de test dont les 36 colonnes (+ reference et devenir) ont ete renommees en francais."""
    from moteur.scoring import libelle_variable
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str)
    renommage = {}
    for colonne in df.columns:
        canonique = moteur.noms_canoniques.get(moteur.normaliser(colonne))
        if canonique:
            renommage[colonne] = "Col. " + libelle_variable(canonique)
    renommage["Reference"], renommage["Target"] = "Matricule", "Statut final"
    return df.rename(columns=renommage), renommage


def test_36_variables_sous_d_autres_noms_donnent_le_meme_tableau(client, moteur, contenu_jeu_de_test):
    """Le cas souleve par l'etudiant : un fichier a 36 variables dont les en-tetes different du jeu d'origine.
    Avec la correspondance etendue aux 36 variables, le tableau est identique au tableau de bord."""
    reference = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    df, renommage = _fichier_renomme(contenu_jeu_de_test, moteur)
    fichier = df.to_csv(index=False).encode("utf-8")
    analyse = client.post("/api/analyser-fichier", data={"fichier": (io.BytesIO(fichier), "x.csv")},
                          content_type="multipart/form-data").json
    assert analyse["mapping_necessaire"] is True
    assert len(analyse["champs_supplementaires"]) == 23
    correspondance = {}
    for ancien, nouveau in renommage.items():
        if ancien == "Reference":
            correspondance["reference"] = nouveau
        elif ancien == "Target":
            correspondance["devenir"] = nouveau
        else:
            correspondance[moteur.noms_canoniques[moteur.normaliser(ancien)]] = nouveau
    assert len(correspondance) == 38
    r = televerser(client, fichier, "36_renommees.csv", mapping=json.dumps(correspondance))
    assert r.status_code == 200 and r.json["variables_reconnues"] == 36 and r.json["moyenne_estimees"] == 0.0
    assert lignes_sans_id(client, reference)[0] == lignes_sans_id(client, r.json["cohorte_id"])[0]


def test_sans_les_variables_supplementaires_le_tableau_differe(client, moteur, contenu_jeu_de_test):
    """Contre-epreuve : si seules les 13 variables principales sont associees, les 23 autres sont estimees."""
    from moteur.referentiels import CHAMPS_FORMULAIRE
    reference = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    df, renommage = _fichier_renomme(contenu_jeu_de_test, moteur)
    correspondance = {c: renommage[next(k for k in renommage if moteur.normaliser(k) == moteur.normaliser(c))] for c in CHAMPS_FORMULAIRE}
    correspondance.update({"reference": "Matricule", "devenir": "Statut final"})
    r = televerser(client, df.to_csv(index=False).encode("utf-8"), "13_sur_36.csv", mapping=json.dumps(correspondance))
    assert r.status_code == 200 and r.json["variables_reconnues"] == 13 and r.json["moyenne_estimees"] == 23.0
    assert lignes_sans_id(client, reference)[0] != lignes_sans_id(client, r.json["cohorte_id"])[0]


def test_colonne_inconnue_dans_un_fichier_complet_declenche_la_correspondance(client, contenu_jeu_de_test):
    df = pd.read_csv(io.BytesIO(contenu_jeu_de_test), dtype=str)
    df["Nom"] = "X"
    analyse = client.post("/api/analyser-fichier", data={"fichier": (io.BytesIO(df.to_csv(index=False).encode()), "x.csv")},
                          content_type="multipart/form-data").json
    assert analyse["mapping_necessaire"] is True and analyse["colonnes_non_reconnues"] == ["Nom"]
    assert analyse["suggestions"]["Course"] == "Course" and analyse["suggestions"]["Gender"] == "Gender"
    # le fichier d'origine, lui, est traite directement
    direct = client.post("/api/analyser-fichier", data={"fichier": (io.BytesIO(contenu_jeu_de_test), "x.csv")},
                         content_type="multipart/form-data").json
    assert direct["mapping_necessaire"] is False


def test_la_correspondance_proposee_automatiquement_donne_le_meme_tableau(client, moteur, contenu_jeu_de_test):
    """Les en-tetes renommes contiennent le nom de la variable : l'analyse les associe seule, l'utilisateur confirme."""
    reference = client.post("/api/cohortes/jeu-de-test").json["cohorte_id"]
    df, _ = _fichier_renomme(contenu_jeu_de_test, moteur)
    fichier = df.to_csv(index=False).encode("utf-8")
    analyse = client.post("/api/analyser-fichier", data={"fichier": (io.BytesIO(fichier), "x.csv")},
                          content_type="multipart/form-data").json
    assert len(analyse["suggestions"]) == 36 + 1                       # 36 variables + la reference (Matricule)
    assert analyse["colonnes_non_reconnues"] == ["Statut final"]       # reste a placer a la main (devenir reel)
    correspondance = {**analyse["suggestions"], "devenir": "Statut final"}
    r = televerser(client, fichier, "auto.csv", mapping=json.dumps(correspondance))
    assert r.status_code == 200 and r.json["variables_reconnues"] == 36
    assert lignes_sans_id(client, reference)[0] == lignes_sans_id(client, r.json["cohorte_id"])[0]
