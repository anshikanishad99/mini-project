"""Trains the disease-prediction model (Scikit-learn RandomForest).

NOTE: no public student dataset is bundled, so this generates a SYNTHETIC dataset
from medically-inspired rules. Replace make_dataset() with a real CSV for better
accuracy. Output is a screening aid, NOT a diagnosis.
"""
import os, json
import numpy as np, pandas as pd, joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score

FEATURES = ["temperature", "cough", "headache", "sore_throat", "body_ache", "fatigue",
            "dizziness", "pale_skin", "water_intake", "sleep_hours", "stress_level", "heart_rate"]
LABELS = ["Healthy", "Fever", "Flu", "Dehydration", "Anemia", "Stress"]
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "health_model.pkl")
METRICS_PATH = os.path.join(os.path.dirname(__file__), "model", "metrics.json")
rng = np.random.default_rng(42)


def _row(label):
    b = lambda p: int(rng.random() < p)
    r = dict(temperature=rng.normal(98.4, .4), cough=b(.08), headache=b(.10), sore_throat=b(.06),
             body_ache=b(.06), fatigue=b(.12), dizziness=b(.03), pale_skin=b(.03),
             water_intake=rng.normal(2.4, .5), sleep_hours=rng.normal(7.3, .8),
             stress_level=int(rng.integers(1, 5)), heart_rate=rng.normal(74, 8))
    if label == "Fever":
        r.update(temperature=rng.normal(101.5, 1), headache=b(.6), body_ache=b(.6), fatigue=b(.6), heart_rate=rng.normal(92, 9))
    elif label == "Flu":
        r.update(temperature=rng.normal(100.5, 1), cough=b(.85), sore_throat=b(.7), body_ache=b(.8),
                 fatigue=b(.8), headache=b(.6), heart_rate=rng.normal(88, 8))
    elif label == "Dehydration":
        r.update(water_intake=rng.normal(.9, .3), headache=b(.7), dizziness=b(.6), fatigue=b(.6),
                 heart_rate=rng.normal(98, 9), temperature=rng.normal(98.8, .5))
    elif label == "Anemia":
        r.update(pale_skin=b(.8), fatigue=b(.9), dizziness=b(.6), headache=b(.4), heart_rate=rng.normal(96, 9))
    elif label == "Stress":
        r.update(stress_level=int(rng.integers(7, 11)), sleep_hours=rng.normal(4.8, 1), headache=b(.6),
                 fatigue=b(.6), heart_rate=rng.normal(86, 8))
    r["temperature"] = float(np.clip(r["temperature"], 96, 106))
    r["water_intake"] = float(np.clip(r["water_intake"], .2, 5))
    r["sleep_hours"] = float(np.clip(r["sleep_hours"], 2, 12))
    r["heart_rate"] = float(np.clip(r["heart_rate"], 45, 150))
    r["label"] = label
    return r


def make_dataset(n_per_class=1500):
    return pd.DataFrame([_row(l) for l in LABELS for _ in range(n_per_class)])


def main():
    df = make_dataset()
    Xtr, Xte, ytr, yte = train_test_split(df[FEATURES], df["label"], test_size=.2, random_state=42, stratify=df["label"])
    clf = RandomForestClassifier(n_estimators=200, random_state=42).fit(Xtr, ytr)
    pred = clf.predict(Xte)
    print(f"Accuracy on synthetic test set: {accuracy_score(yte, pred):.3f}")
    print(classification_report(yte, pred))
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    import sklearn
    cv = cross_val_score(RandomForestClassifier(n_estimators=100, random_state=42), df[FEATURES], df["label"], cv=5)
    print(f"5-fold cross-validation accuracy: {cv.mean():.3f} (+/- {cv.std():.3f})")
    with open(METRICS_PATH, "w") as f:      # shown on the Technologies page
        json.dump(dict(accuracy=round(float(accuracy_score(yte, pred)), 4), cv_accuracy=round(float(cv.mean()), 4),
                       samples=len(df), classes=LABELS, sklearn_version=sklearn.__version__,
                       importances={k: round(float(v), 4) for k, v in
                                    sorted(zip(FEATURES, clf.feature_importances_), key=lambda t: -t[1])}), f)
    print("Saved model to", MODEL_PATH)


if __name__ == "__main__":
    main()
