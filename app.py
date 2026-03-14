from flask import Flask, request, render_template_string
import json
import joblib
import pandas as pd

app = Flask(__name__)

fighters = json.load(open("fighters.json"))

winner_model = joblib.load("model_winner.joblib")
method_model = joblib.load("model_method.joblib")
meta = json.load(open("model_meta.json"))

feature_cols = meta["feature_cols"]

def get_float(v):
    try:
        return float(v)
    except:
        return 0

def fighter_stats(f):
    return {
        "slpm": get_float(f.get("slpm")),
        "sapm": get_float(f.get("sapm")),
        "str_acc": get_float(f.get("str_acc")),
        "str_def": get_float(f.get("str_def")),
        "td_avg": get_float(f.get("td_avg")),
        "td_acc": get_float(f.get("td_acc")),
        "td_def": get_float(f.get("td_def")),
        "sub_avg": get_float(f.get("sub_avg")),
        "ko_rate": get_float(f.get("ko_rate")),
        "sub_rate": get_float(f.get("sub_rate")),
        "decision_rate": get_float(f.get("decision_rate")),
        "finish_rate": get_float(f.get("finish_rate")),
        "total_fights": get_float(f.get("total_fights")),
        "win_rate": get_float(f.get("wins")) / max(1,get_float(f.get("total_fights")))
    }

def build_features(f1,f2):

    s1 = fighter_stats(f1)
    s2 = fighter_stats(f2)

    row = {}

    for k in s1:
        row["f_"+k] = s1[k]
        row["o_"+k] = s2[k]
        row["diff_"+k] = s1[k] - s2[k]

    row["ratio_slpm_sapm"] = (s1["slpm"]+1e-6)/(s2["sapm"]+1e-6)
    row["ratio_tdavg_tddef"] = (s1["td_avg"]+1e-6)/(s2["td_def"]+1e-6)
    row["ratio_subavg_tddef"] = (s1["sub_avg"]+1e-6)/(s2["td_def"]+1e-6)

    row["scheduled_rounds"] = 3

    return pd.DataFrame([row])[feature_cols]

@app.route("/")
def home():

    names = sorted([f["name"] for f in fighters])

    return render_template_string("""
    <h1>UFC AI Fight Predictor</h1>
    <form action="/predict">
    Fighter A:<br>
    <input name="a"><br>
    Fighter B:<br>
    <input name="b"><br>
    <button>Predict</button>
    </form>
    """)

@app.route("/predict")
def predict():

    a = request.args.get("a")
    b = request.args.get("b")

    f1 = next(x for x in fighters if x["name"]==a)
    f2 = next(x for x in fighters if x["name"]==b)

    X = build_features(f1,f2)

    prob = winner_model.predict_proba(X)[0][1]

    methods = method_model.predict_proba(X)[0]
    classes = method_model.classes_

    method_probs = dict(zip(classes,methods))

    return {
        "fight": f"{a} vs {b}",
        "fighter_A_win_probability": float(prob),
        "fighter_B_win_probability": float(1-prob),
        "method_probabilities": method_probs
    }

if __name__ == "__main__":
    app.run()
