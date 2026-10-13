"""
Train an SVM and a small MLP on ml/data/gesture_data.csv, report accuracy / weighted F1 /
confusion matrix on a held-out test set, and save the better model to models/gesture_model.joblib
(Sketch mode loads it automatically on the next backend start).

Run from the project root:
    python -m ml.train_gesture
    python -m ml.train_gesture --holdout-person asha      # test on a teammate the model never saw

Needs:  pip install -r backend/requirements-ml.txt
"""
import argparse
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import (ConfusionMatrixDisplay, accuracy_score, classification_report,
                             confusion_matrix, f1_score)
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CSV_PATH = HERE / "data" / "gesture_data.csv"
MODEL_PATH = ROOT / "models" / "gesture_model.joblib"
REPORT_DIR = HERE / "reports"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout-person", default=None)
    args = parser.parse_args()

    df = pd.read_csv(CSV_PATH)
    if "label" not in df.columns:
        raise SystemExit("gesture_data.csv has no header row - see README (\"Fixing a CSV without header\").")
    print("Samples per label:\n", df["label"].value_counts(), "\n")
    print("Samples per person:\n", df["person"].value_counts(), "\n")
    feature_cols = [c for c in df.columns if c.startswith("f")]

    if args.holdout_person:
        train_df, test_df = df[df["person"] != args.holdout_person], df[df["person"] == args.holdout_person]
        if test_df.empty or train_df.empty:
            raise SystemExit(f"Need data from '{args.holdout_person}' AND from at least one other person.")
        X_train, y_train, X_test, y_test = train_df[feature_cols], train_df["label"], test_df[feature_cols], test_df["label"]
        print(f"Test set = all data from '{args.holdout_person}'\n")
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            df[feature_cols], df["label"], test_size=0.2, stratify=df["label"], random_state=42)

    X_train, X_test = X_train.to_numpy(), X_test.to_numpy()      # plain arrays: no feature-name warnings later

    models = {
        "SVM": make_pipeline(StandardScaler(), SVC(kernel="rbf", C=10, gamma="scale")),
        "MLP": make_pipeline(StandardScaler(), MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=500, random_state=42)),
    }
    labels = sorted(df["label"].unique())
    REPORT_DIR.mkdir(exist_ok=True)
    best_name, best_f1, best_model = None, -1.0, None

    for name, model in models.items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        acc, f1 = accuracy_score(y_test, pred), f1_score(y_test, pred, average="weighted")
        print(f"===== {name} =====\nAccuracy: {acc:.4f} | Weighted F1: {f1:.4f}")
        print(classification_report(y_test, pred, digits=3))
        ConfusionMatrixDisplay(confusion_matrix(y_test, pred, labels=labels), display_labels=labels).plot(cmap="Blues")
        plt.title(f"{name} confusion matrix")
        plt.savefig(REPORT_DIR / f"confusion_{name.lower()}.png", dpi=150, bbox_inches="tight")
        plt.close()
        if f1 > best_f1:
            best_name, best_f1, best_model = name, f1, model

    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)
    print(f"Saved best model ({best_name}, weighted F1 {best_f1:.4f}) to {MODEL_PATH}")
    print(f"Confusion matrix images are in {REPORT_DIR}/")


if __name__ == "__main__":
    main()
