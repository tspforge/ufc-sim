import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FIGHTERS_FILE = "fighters.json"
HISTORICAL_FILE = "historical_fights.csv"
WINNER_MODEL_FILE = "model_winner.joblib"
METHOD_MODEL_FILE = "model_method.joblib"
META_FILE = "model_meta.json"


def load_fighters() -> Dict[str, Dict]:
    with open(FIGHTERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    fighters = {}
    for row in data:
        name = row.get("name") or f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
        if name:
            row["name"] = name
            fighters[name] = row
    return fighters


def get_float(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def stat_block(f: Dict) -> Dict[str, float]:
    total_fights = max(1.0, get_float(f.get("total_fights"), 1.0))
    wins = get_float(f.get("wins"), 0.0)

    return {
        "slpm": get_float(f.get("slpm"), 0.0),
        "sapm": get_float(f.get("sapm"), 0.0),
        "str_acc": get_float(f.get("str_acc"), 0.0),
        "str_def": get_float(f.get("str_def"), 0.0),
        "td_avg": get_float(f.get("td_avg"), 0.0),
        "td_acc": get_float(f.get("td_acc"), 0.0),
        "td_def": get_float(f.get("td_def"), 0.0),
        "sub_avg": get_float(f.get("sub_avg"), 0.0),
        "ko_rate": get_float(f.get("ko_rate"), 0.0),
        "sub_rate": get_float(f.get("sub_rate"), 0.0),
        "decision_rate": get_float(f.get("decision_rate"), 0.0),
        "finish_rate": get_float(f.get("finish_rate"), 0.0),
        "win_rate": wins / total_fights,
        "total_fights": total_fights,
    }


def method_label(result: str, method_group: str) -> str:
    if result == "W":
        prefix = "fighter"
    elif result == "L":
        prefix = "opponent"
    else:
        return "draw"

    if method_group == "ko":
        return f"{prefix}_ko"
    if method_group == "sub":
        return f"{prefix}_sub"
    return f"{prefix}_dec"


def build_features(df: pd.DataFrame, fighters: Dict[str, Dict]) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    rows: List[Dict] = []
    winner_labels: List[int] = []
    method_labels: List[str] = []

    for _, row in df.iterrows():
        fighter_name = row["fighter_name"]
        opponent_name = row["opponent_name"]

        if fighter_name not in fighters or opponent_name not in fighters:
            continue

        fighter = stat_block(fighters[fighter_name])
        opponent = stat_block(fighters[opponent_name])

        feat = {
            "fighter_name": fighter_name,
            "opponent_name": opponent_name,
            "event_date": row["event_date"],
            "scheduled_rounds": 5 if str(row["round"]).strip() == "5" else 3,
        }

        for key in fighter.keys():
            feat[f"f_{key}"] = fighter[key]
            feat[f"o_{key}"] = opponent[key]
            feat[f"diff_{key}"] = fighter[key] - opponent[key]

        feat["ratio_slpm_sapm"] = (fighter["slpm"] + 1e-6) / (opponent["sapm"] + 1e-6)
        feat["ratio_tdavg_tddef"] = (fighter["td_avg"] + 1e-6) / (opponent["td_def"] + 1e-6)
        feat["ratio_subavg_tddef"] = (fighter["sub_avg"] + 1e-6) / (opponent["td_def"] + 1e-6)

        rows.append(feat)
        winner_labels.append(1 if row["result"] == "W" else 0)
        method_labels.append(method_label(row["result"], row["method_group"]))

    X = pd.DataFrame(rows)
    y_winner = pd.Series(winner_labels)
    y_method = pd.Series(method_labels)

    return X, y_winner, y_method


def split_by_date(X: pd.DataFrame, y_winner: pd.Series, y_method: pd.Series):
    X = X.copy()
    X["event_date"] = pd.to_datetime(X["event_date"], errors="coerce")
    X = X.sort_values("event_date").reset_index(drop=True)

    y_winner = y_winner.iloc[X.index].reset_index(drop=True)
    y_method = y_method.iloc[X.index].reset_index(drop=True)

    split_idx = int(len(X) * 0.8)
    train_idx = X.index[:split_idx]
    test_idx = X.index[split_idx:]

    X_train = X.iloc[train_idx].reset_index(drop=True)
    X_test = X.iloc[test_idx].reset_index(drop=True)

    y_train_w = y_winner.iloc[train_idx].reset_index(drop=True)
    y_test_w = y_winner.iloc[test_idx].reset_index(drop=True)

    y_train_m = y_method.iloc[train_idx].reset_index(drop=True)
    y_test_m = y_method.iloc[test_idx].reset_index(drop=True)

    return X_train, X_test, y_train_w, y_test_w, y_train_m, y_test_m


def make_preprocessor(feature_cols: List[str]):
    return ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                feature_cols,
            )
        ]
    )


def main():
    fighters = load_fighters()
    history = pd.read_csv(HISTORICAL_FILE)

    X, y_winner, y_method = build_features(history, fighters)

    keep_cols = [c for c in X.columns if c not in {"fighter_name", "opponent_name", "event_date"}]
    X_train, X_test, y_train_w, y_test_w, y_train_m, y_test_m = split_by_date(X, y_winner, y_method)

    pre = make_preprocessor(keep_cols)

    winner_base = HistGradientBoostingClassifier(
        max_depth=6,
        learning_rate=0.05,
        max_iter=300,
        random_state=42,
    )

    winner_model = Pipeline(
        steps=[
            ("prep", pre),
            ("model", CalibratedClassifierCV(winner_base, method="sigmoid", cv=3)),
        ]
    )

    method_model = Pipeline(
        steps=[
            ("prep", pre),
            ("model", HistGradientBoostingClassifier(
                max_depth=6,
                learning_rate=0.05,
                max_iter=350,
                random_state=42,
            )),
        ]
    )

    winner_model.fit(X_train[keep_cols], y_train_w)
    method_model.fit(X_train[keep_cols], y_train_m)

    winner_probs = winner_model.predict_proba(X_test[keep_cols])[:, 1]
    winner_preds = (winner_probs >= 0.5).astype(int)

    acc = accuracy_score(y_test_w, winner_preds)
    brier = brier_score_loss(y_test_w, winner_probs)
    ll = log_loss(y_test_w, winner_probs)

    method_preds = method_model.predict(X_test[keep_cols])
    method_acc = accuracy_score(y_test_m, method_preds)

    print(f"Winner accuracy: {acc:.4f}")
    print(f"Winner brier:    {brier:.4f}")
    print(f"Winner logloss:  {ll:.4f}")
    print(f"Method accuracy: {method_acc:.4f}")
    print(f"Train rows:      {len(X_train)}")
    print(f"Test rows:       {len(X_test)}")

    joblib.dump(winner_model, WINNER_MODEL_FILE)
    joblib.dump(method_model, METHOD_MODEL_FILE)

    meta = {
        "feature_cols": keep_cols,
        "winner_accuracy": acc,
        "winner_brier": brier,
        "winner_logloss": ll,
        "method_accuracy": method_acc,
        "train_rows": len(X_train),
        "test_rows": len(X_test),
        "winner_model_file": WINNER_MODEL_FILE,
        "method_model_file": METHOD_MODEL_FILE,
    }

    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Saved {WINNER_MODEL_FILE}, {METHOD_MODEL_FILE}, and {META_FILE}")


if __name__ == "__main__":
    main()
