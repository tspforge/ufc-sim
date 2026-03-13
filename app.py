from flask import Flask, request, render_template_string
import json
import os
import random

app = Flask(__name__)

DB_FILE = "fighters.json"

fighter_list = []
fighters = {}
debug_info = {
    "db_file": DB_FILE,
    "cwd": os.getcwd(),
    "file_exists": os.path.exists(DB_FILE),
    "file_size": 0,
    "data_type": "none",
    "raw_count": 0,
    "loaded_count": 0,
    "sample_keys": [],
    "sample_item": None,
    "error": "",
    "repo_files": sorted(os.listdir(".")),
}


def build_fighter_name(fighter):
    if not isinstance(fighter, dict):
        return ""

    for key in ["name", "fighter_name", "full_name"]:
        value = str(fighter.get(key, "")).strip()
        if value:
            return value

    first = str(fighter.get("first_name", "")).strip()
    last = str(fighter.get("last_name", "")).strip()
    combined = f"{first} {last}".strip()
    if combined:
        return combined

    first = str(fighter.get("firstname", "")).strip()
    last = str(fighter.get("lastname", "")).strip()
    combined = f"{first} {last}".strip()
    if combined:
        return combined

    return ""


try:
    if os.path.exists(DB_FILE):
        debug_info["file_size"] = os.path.getsize(DB_FILE)

        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            fighter_list = data
            debug_info["data_type"] = "list"
            debug_info["raw_count"] = len(data)

        elif isinstance(data, dict):
            debug_info["data_type"] = "dict"
            if "fighters" in data and isinstance(data["fighters"], list):
                fighter_list = data["fighters"]
                debug_info["raw_count"] = len(fighter_list)
            else:
                debug_info["raw_count"] = len(data)

        else:
            debug_info["data_type"] = str(type(data))

        if fighter_list:
            first_item = fighter_list[0]
            if isinstance(first_item, dict):
                debug_info["sample_keys"] = list(first_item.keys())[:25]
                debug_info["sample_item"] = {
                    k: first_item[k] for k in list(first_item.keys())[:10]
                }
            else:
                debug_info["sample_item"] = str(first_item)

    for fighter in fighter_list:
        if not isinstance(fighter, dict):
            continue

        name = build_fighter_name(fighter)
        if not name:
            continue

        fighter["name"] = name
        fighters[name] = fighter

    debug_info["loaded_count"] = len(fighters)

except Exception as e:
    debug_info["error"] = str(e)


def clamp(value, low, high):
    return max(low, min(high, value))


def get_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def normalize_fighter_stats(f):
    slpm = get_float(f.get("slpm"), 2.5)
    sapm = get_float(f.get("sapm"), 2.5)
    str_acc = get_float(f.get("str_acc"), 45.0)
    str_def = get_float(f.get("str_def"), 50.0)
    td_avg = get_float(f.get("td_avg"), 0.5)
    td_acc = get_float(f.get("td_acc"), 35.0)
    td_def = get_float(f.get("td_def"), 55.0)
    sub_avg = get_float(f.get("sub_avg"), 0.2)

    total_fights = int(get_float(f.get("total_fights"), 1))
    wins = int(get_float(f.get("wins"), 0))

    ko_rate = get_float(f.get("ko_rate"), 0.20)
    sub_rate = get_float(f.get("sub_rate"), 0.10)
    decision_rate = get_float(f.get("decision_rate"), 0.70)

    win_rate = wins / total_fights if total_fights > 0 else 0.5
    experience_factor = clamp(total_fights / 20.0, 0.4, 1.2)

    return {
        "name": f.get("name", "Unknown"),
        "slpm": slpm,
        "sapm": sapm,
        "str_acc": str_acc,
        "str_def": str_def,
        "td_avg": td_avg,
        "td_acc": td_acc,
        "td_def": td_def,
        "sub_avg": sub_avg,
        "ko_rate": ko_rate,
        "sub_rate": sub_rate,
        "decision_rate": decision_rate,
        "win_rate": win_rate,
        "experience_factor": experience_factor,
    }


def build_matchup_probabilities(a_raw, b_raw, rounds):
    a = normalize_fighter_stats(a_raw)
    b = normalize_fighter_stats(b_raw)

    a_strike_score = (
        (a["slpm"] * (a["str_acc"] / 100.0))
        - (b["sapm"] * (b["str_def"] / 100.0))
    )
    b_strike_score = (
        (b["slpm"] * (b["str_acc"] / 100.0))
        - (a["sapm"] * (a["str_def"] / 100.0))
    )

    a_grapple_score = (a["td_avg"] * (a["td_acc"] / 100.0)) - (b["td_def"] / 100.0)
    b_grapple_score = (b["td_avg"] * (b["td_acc"] / 100.0)) - (a["td_def"] / 100.0)

    a_total = (
        a_strike_score * 1.2
        + a_grapple_score * 0.9
        + a["win_rate"] * 1.0
        + a["experience_factor"] * 0.5
    )
    b_total = (
        b_strike_score * 1.2
        + b_grapple_score * 0.9
        + b["win_rate"] * 1.0
        + b["experience_factor"] * 0.5
    )

    raw_a = max(0.05, a_total + 2.5)
    raw_b = max(0.05, b_total + 2.5)
    total = raw_a + raw_b

    a_win_prob = raw_a / total
    b_win_prob = raw_b / total

    if rounds == 5:
        finish_multiplier = 1.08
        decision_multiplier = 1.05
    else:
        finish_multiplier = 1.00
        decision_multiplier = 1.00

    a_ko_weight = max(0.01, a["ko_rate"] * (1 + max(0, a_strike_score) * 0.10)) * finish_multiplier
    a_sub_weight = max(0.01, a["sub_rate"] * (1 + max(0, a_grapple_score) * 0.15)) * finish_multiplier
    a_dec_weight = max(0.01, a["decision_rate"]) * decision_multiplier

    b_ko_weight = max(0.01, b["ko_rate"] * (1 + max(0, b_strike_score) * 0.10)) * finish_multiplier
    b_sub_weight = max(0.01, b["sub_rate"] * (1 + max(0, b_grapple_score) * 0.15)) * finish_multiplier
    b_dec_weight = max(0.01, b["decision_rate"]) * decision_multiplier

    a_method_total = a_ko_weight + a_sub_weight + a_dec_weight
    b_method_total = b_ko_weight + b_sub_weight + b_dec_weight

    return {
        f'{a["name"]} KO/TKO': a_win_prob * (a_ko_weight / a_method_total),
        f'{a["name"]} Submission': a_win_prob * (a_sub_weight / a_method_total),
        f'{a["name"]} Decision': a_win_prob * (a_dec_weight / a_method_total),
        f'{b["name"]} KO/TKO': b_win_prob * (b_ko_weight / b_method_total),
        f'{b["name"]} Submission': b_win_prob * (b_sub_weight / b_method_total),
        f'{b["name"]} Decision': b_win_prob * (b_dec_weight / b_method_total),
    }


def simulate_fight(fighter_a, fighter_b, rounds):
    probs = build_matchup_probabilities(fighters[fighter_a], fighters[fighter_b], rounds)
    outcomes = list(probs.keys())
    weights = list(probs.values())
    return random.choices(outcomes, weights=weights, k=1)[0]


def monte_carlo(fighter_a, fighter_b, rounds, runs):
    method_counts = {
        f"{fighter_a} KO/TKO": 0,
        f"{fighter_a} Submission": 0,
        f"{fighter_a} Decision": 0,
        f"{fighter_b} KO/TKO": 0,
        f"{fighter_b} Submission": 0,
        f"{fighter_b} Decision": 0,
    }

    for _ in range(runs):
        outcome = simulate_fight(fighter_a, fighter_b, rounds)
        method_counts[outcome] += 1

    method_percentages = {
        outcome: round((count / runs) * 100, 2)
        for outcome, count in method_counts.items()
    }

    fighter_a_win_pct = round(
        method_percentages[f"{fighter_a} KO/TKO"]
        + method_percentages[f"{fighter_a} Submission"]
        + method_percentages[f"{fighter_a} Decision"],
        2
    )
    fighter_b_win_pct = round(
        method_percentages[f"{fighter_b} KO/TKO"]
        + method_percentages[f"{fighter_b} Submission"]
        + method_percentages[f"{fighter_b} Decision"],
        2
    )

    ranked_methods = sorted(
        method_percentages.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return {
        "fight": f"{fighter_a} vs {fighter_b}",
        "rounds": rounds,
        "simulations": runs,
        "win_percentages": {
            fighter_a: fighter_a_win_pct,
            fighter_b: fighter_b_win_pct
        },
        "method_breakdown": ranked_methods
    }


HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>UFC Sim</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0b0d12;
            color: white;
            margin: 0;
            padding: 40px 20px;
        }
        .wrap {
            max-width: 900px;
            margin: 0 auto;
        }
        h1 {
            margin-top: 0;
            font-size: 48px;
        }
        p {
            color: #b9c0cc;
        }
        form {
            background: #161a22;
            padding: 24px;
            border-radius: 16px;
            margin-top: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
        }
        input, select, button {
            width: 100%;
            padding: 14px;
            margin-bottom: 18px;
            border-radius: 10px;
            border: none;
            font-size: 16px;
            box-sizing: border-box;
        }
        button {
            background: #ff9800;
            color: black;
            font-weight: bold;
            cursor: pointer;
        }
        .debug {
            margin-top: 24px;
            background: #161a22;
            padding: 18px;
            border-radius: 16px;
        }
        .debug pre {
            white-space: pre-wrap;
            word-break: break-word;
            color: #9fd3ff;
        }
        .hint {
            color: #8fa0b5;
            margin-top: -10px;
            margin-bottom: 18px;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="wrap">
        <h1>UFC Fight Simulator</h1>
        <p>Fighters in database: <strong>{{ fighter_count }}</strong></p>

        <form action="/simulate" method="get">
            <label for="fighter_a">Fighter A</label>
            <input
                list="fighter-list"
                name="fighter_a"
                id="fighter_a"
                placeholder="Start typing a fighter name..."
                autocomplete="off"
                required
            >

            <label for="fighter_b">Fighter B</label>
            <input
                list="fighter-list"
                name="fighter_b"
                id="fighter_b"
                placeholder="Start typing a fighter name..."
                autocomplete="off"
                required
            >

            <datalist id="fighter-list">
                {% for fighter in fighter_names %}
                <option value="{{ fighter }}">
                {% endfor %}
            </datalist>

            <div class="hint">Type a few letters like “jon”, “islam”, or “pereira”.</div>

            <label for="rounds">Rounds</label>
            <select name="rounds" id="rounds">
                <option value="3">3 Rounds</option>
                <option value="5">5 Rounds</option>
            </select>

            <label for="runs">Simulations</label>
            <input type="number" name="runs" id="runs" value="100000" min="1000" step="1000">

            <button type="submit">Run Simulation</button>
        </form>

        <div class="debug">
            <h3>Debug</h3>
            <pre>{{ debug_info }}</pre>
        </div>
    </div>
</body>
</html>
"""

RESULT_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>UFC Sim Results</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #0b0d12;
            color: white;
            margin: 0;
            padding: 40px 20px;
        }
        .wrap {
            max-width: 980px;
            margin: 0 auto;
        }
        h1 {
            font-size: 46px;
            margin: 0 0 10px;
        }
        .sub {
            color: #9fb0c5;
            margin-bottom: 28px;
            font-size: 18px;
        }
        .topbar {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 18px;
            margin-bottom: 24px;
        }
        .card {
            background: #161a22;
            border-radius: 18px;
            padding: 22px;
            box-shadow: 0 8px 24px rgba(0,0,0,.20);
        }
        .fighter-name {
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 10px;
        }
        .win-pct {
            font-size: 54px;
            font-weight: 900;
            line-height: 1;
            color: #ff9800;
        }
        .meta {
            color: #9fb0c5;
            margin-top: 8px;
            font-size: 14px;
        }
        .section-title {
            font-size: 24px;
            font-weight: 800;
            margin: 26px 0 14px;
        }
        .method-list {
            display: grid;
            gap: 12px;
        }
        .method-row {
            background: #161a22;
            border-radius: 14px;
            padding: 16px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
        }
        .method-name {
            font-size: 18px;
            font-weight: 700;
        }
        .method-pct {
            font-size: 22px;
            font-weight: 900;
            color: #7cf29a;
            white-space: nowrap;
        }
        .actions {
            margin-top: 28px;
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }
        .btn {
            display: inline-block;
            background: #ff9800;
            color: black;
            text-decoration: none;
            font-weight: 800;
            padding: 14px 18px;
            border-radius: 12px;
        }
        .btn.secondary {
            background: #232835;
            color: white;
        }
        @media (max-width: 700px) {
            .topbar {
                grid-template-columns: 1fr;
            }
            .win-pct {
                font-size: 42px;
            }
            .fighter-name {
                font-size: 24px;
            }
            .method-name {
                font-size: 16px;
            }
            .method-pct {
                font-size: 18px;
            }
        }
    </style>
</head>
<body>
    <div class="wrap">
        <h1>{{ fight }}</h1>
        <div class="sub">{{ rounds }} rounds • {{ simulations }} simulations</div>

        <div class="topbar">
            <div class="card">
                <div class="fighter-name">{{ fighter_a }}</div>
                <div class="win-pct">{{ fighter_a_win }}%</div>
                <div class="meta">Overall win probability</div>
            </div>

            <div class="card">
                <div class="fighter-name">{{ fighter_b }}</div>
                <div class="win-pct">{{ fighter_b_win }}%</div>
                <div class="meta">Overall win probability</div>
            </div>
        </div>

        <div class="section-title">Method Breakdown</div>
        <div class="method-list">
            {% for method, pct in method_breakdown %}
            <div class="method-row">
                <div class="method-name">{{ method }}</div>
                <div class="method-pct">{{ pct }}%</div>
            </div>
            {% endfor %}
        </div>

        <div class="actions">
            <a class="btn" href="/">Run Another Simulation</a>
            <a class="btn secondary" href="/simulate?fighter_a={{ fighter_a | urlencode }}&fighter_b={{ fighter_b | urlencode }}&rounds={{ rounds }}&runs={{ simulations }}&format=json">View JSON</a>
        </div>
    </div>
</body>
</html>
"""

@app.route("/")
def home():
    fighter_names = sorted(fighters.keys())
    return render_template_string(
        HOME_HTML,
        fighter_names=fighter_names,
        fighter_count=len(fighter_names),
        debug_info=json.dumps(debug_info, indent=2),
    )

@app.route("/simulate")
def simulate():
    fighter_a = request.args.get("fighter_a")
    fighter_b = request.args.get("fighter_b")
    rounds = int(request.args.get("rounds", 3))
    runs = int(request.args.get("runs", 100000))
    output_format = request.args.get("format", "").lower()

    if fighter_a not in fighters or fighter_b not in fighters:
        return render_template_string(
            """
            <html><body style="font-family:Arial;background:#0b0d12;color:white;padding:40px;">
            <h1>Fighter not found</h1>
            <p>Make sure you selected valid fighter names from the search box.</p>
            <p><a href="/" style="color:#ff9800;">Go back</a></p>
            </body></html>
            """
        ), 400

    if fighter_a == fighter_b:
        return render_template_string(
            """
            <html><body style="font-family:Arial;background:#0b0d12;color:white;padding:40px;">
            <h1>Invalid matchup</h1>
            <p>Fighter A and Fighter B must be different.</p>
            <p><a href="/" style="color:#ff9800;">Go back</a></p>
            </body></html>
            """
        ), 400

    if rounds not in [3, 5]:
        return render_template_string(
            """
            <html><body style="font-family:Arial;background:#0b0d12;color:white;padding:40px;">
            <h1>Invalid rounds</h1>
            <p>Rounds must be 3 or 5.</p>
            <p><a href="/" style="color:#ff9800;">Go back</a></p>
            </body></html>
            """
        ), 400

    if runs <= 0:
        return render_template_string(
            """
            <html><body style="font-family:Arial;background:#0b0d12;color:white;padding:40px;">
            <h1>Invalid simulation count</h1>
            <p>Simulation count must be greater than 0.</p>
            <p><a href="/" style="color:#ff9800;">Go back</a></p>
            </body></html>
            """
        ), 400

    results = monte_carlo(fighter_a, fighter_b, rounds, runs)

    if output_format == "json":
        return {
            "fight": results["fight"],
            "rounds": results["rounds"],
            "simulations": results["simulations"],
            "win_percentages": results["win_percentages"],
            "method_breakdown": {k: v for k, v in results["method_breakdown"]}
        }

    return render_template_string(
        RESULT_HTML,
        fight=results["fight"],
        rounds=results["rounds"],
        simulations=results["simulations"],
        fighter_a=fighter_a,
        fighter_b=fighter_b,
        fighter_a_win=results["win_percentages"][fighter_a],
        fighter_b_win=results["win_percentages"][fighter_b],
        method_breakdown=results["method_breakdown"],
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
