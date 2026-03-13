from flask import Flask, request, jsonify
import random

app = Flask(__name__)

# -------------------------
# Fighter Profiles
# -------------------------

fighters = {
    "Holloway": {
        "ko": 0.30,
        "sub": 0.04,
        "decision": 0.66
    },
    "Oliveira": {
        "ko": 0.22,
        "sub": 0.40,
        "decision": 0.38
    },
    "Topuria": {
        "ko": 0.55,
        "sub": 0.10,
        "decision": 0.35
    },
    "Makhachev": {
        "ko": 0.18,
        "sub": 0.42,
        "decision": 0.40
    }
}

# -------------------------
# Fight Simulation
# -------------------------

def simulate_fight(fighter_a, fighter_b, rounds):
    a_stats = fighters[fighter_a]
    b_stats = fighters[fighter_b]

    # More rounds = slightly more finish opportunities
    finish_multiplier = 1.25 if rounds == 5 else 1.0

    outcomes = [
        f"{fighter_a} KO/TKO",
        f"{fighter_a} Submission",
        f"{fighter_a} Decision",
        f"{fighter_b} KO/TKO",
        f"{fighter_b} Submission",
        f"{fighter_b} Decision"
    ]

    weights = [
        a_stats["ko"] * finish_multiplier,
        a_stats["sub"] * finish_multiplier,
        a_stats["decision"],
        b_stats["ko"] * finish_multiplier,
        b_stats["sub"] * finish_multiplier,
        b_stats["decision"]
    ]

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

    # Method percentages
    method_percentages = {}
    for outcome, count in method_counts.items():
        method_percentages[outcome] = round((count / runs) * 100, 2)

    # Overall win percentages
    fighter_a_win_pct = round(
        method_percentages[f"{fighter_a} KO/TKO"] +
        method_percentages[f"{fighter_a} Submission"] +
        method_percentages[f"{fighter_a} Decision"],
        2
    )

    fighter_b_win_pct = round(
        method_percentages[f"{fighter_b} KO/TKO"] +
        method_percentages[f"{fighter_b} Submission"] +
        method_percentages[f"{fighter_b} Decision"],
        2
    )

    # Ranked outcomes by likelihood
    ranked_methods = dict(
        sorted(method_percentages.items(), key=lambda x: x[1], reverse=True)
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

# -------------------------
# Routes
# -------------------------

@app.route("/")
def home():
    return """
    <h1>UFC Fight Simulator</h1>
    <p>Examples:</p>
    <ul>
        <li><a href="/simulate?fighter_a=Holloway&fighter_b=Oliveira&rounds=5&runs=100000">Holloway vs Oliveira (5 rounds)</a></li>
        <li><a href="/simulate?fighter_a=Topuria&fighter_b=Makhachev&rounds=3&runs=100000">Topuria vs Makhachev (3 rounds)</a></li>
    </ul>
    <p>Change fighter names, rounds, and runs in the URL.</p>
    """


@app.route("/simulate")
def simulate():
    fighter_a = request.args.get("fighter_a")
    fighter_b = request.args.get("fighter_b")
    rounds = int(request.args.get("rounds", 3))
    runs = int(request.args.get("runs", 100000))

    if fighter_a not in fighters or fighter_b not in fighters:
        return jsonify({
            "error": "fighter not found",
            "available_fighters": list(fighters.keys())
        }), 400

    if rounds not in [3, 5]:
        return jsonify({
            "error": "rounds must be 3 or 5"
        }), 400

    if runs <= 0:
        return jsonify({
            "error": "runs must be greater than 0"
        }), 400

    results = monte_carlo(fighter_a, fighter_b, rounds, runs)
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
