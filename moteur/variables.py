"""Variables par moment de prédiction (T0, T1, T2) et prétraitement appris dans chaque pli.

Copie conforme de src/abandon_universitaire/variables.py du projet de recherche
(github.com/onelngoma-source/abandon-universitaire) : l'application calcule les variables
exactement comme à l'entraînement.
"""

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NOMINALES = ["Marital status", "Application mode", "Course", "Previous qualification",
             "Mother's qualification", "Father's qualification", "Mother's occupation", "Father's occupation"]
BINAIRES = ["Daytime/evening attendance", "Displaced", "Educational special needs", "Debtor",
            "Tuition fees up to date", "Gender", "Scholarship holder", "International"]
FINANCIERES = ["Debtor", "Tuition fees up to date"]
NUMERIQUES_T0 = ["Application order", "Previous qualification (grade)", "Admission grade", "Age at enrollment"]
ECONOMIQUES = ["Unemployment rate", "Inflation rate", "GDP"]
MOMENTS = {"T0": [], "T1": ["1st"], "T2": ["1st", "2nd"]}


def semestre(s: str) -> list[str]:
    return [f"Curricular units {s} sem ({k})"
            for k in ("credited", "enrolled", "evaluations", "approved", "grade", "without evaluations")]


def preparer(df, moment: str, avec_financieres: bool = True):
    """Variables connues au moment donné. Aucune opération apprise ici (pas de fuite)."""
    X = df.copy()
    numeriques = list(NUMERIQUES_T0)
    for s in MOMENTS[moment]:
        cols = semestre(s)
        inscrites, validees, note = cols[1], cols[3], cols[4]
        X[note] = X[note].where(X[validees] > 0)  # moyenne indéfinie si aucune unité validée
        taux = f"taux_validation_{s}"
        X[taux] = (X[validees] / X[inscrites]).where(X[inscrites] > 0)
        numeriques += cols + [taux]
    binaires = [b for b in BINAIRES if avec_financieres or b not in FINANCIERES]
    y = (df["Target"] == "Dropout").astype(int).to_numpy() if "Target" in df else None
    return X[NOMINALES + binaires + numeriques], y, NOMINALES, binaires, numeriques


def pretraitement(nominales, binaires, numeriques) -> ColumnTransformer:
    """Indicatrices (catégories de moins de 20 étudiants regroupées), imputation par la médiane
    avec indicateur de valeur manquante, normalisation. Tout est appris dans le pli d'entraînement."""
    return ColumnTransformer([
        ("nominales", OneHotEncoder(min_frequency=20, handle_unknown="infrequent_if_exist",
                                    sparse_output=False), nominales),
        ("binaires", "passthrough", binaires),
        ("numeriques", make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                                     StandardScaler()), numeriques),
    ])
