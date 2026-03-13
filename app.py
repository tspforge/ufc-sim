from flask import Flask, request, jsonify
import random

app = Flask(__name__)

# -----------------------------
# Fighter Profiles (example)
# -----------------------------

fighters = {
    "Holloway": {
        "ko_power": 0.28,
        "submission": 0.05,
        "decision": 0.67
    },
    "Oliveira": {
        "ko_power": 0.22,
        "submission": 0.38,
        "decision": 0.40
    },
    "Makhachev": {
        "ko_power": 0.18,
        "submission": 0.42,
        "decision": 0.40
    },
    "Topuria": {
        "ko_power": 0.55,
        "submission": 0.10,
        "decision": 0.35
    }
}

# -----------------------------
# Fight Simulation
# -----------------------------

def simulate_fight(a, b):

    a_profile = fighters[a]
    b_profile = fighters[b]

    outcomes = [
        f"{a} KO/TKO",
        f"{a} Submission",
        f"{a} Decision",
        f"{b} KO/TKO",
        f"{b} Submission",
        f"{b} Decision"
    ]

    weights = [
        a_profile["ko_power"],
        a_profile["submission"],
        a_profile["decision"],
        b_profile["ko_power"],
        b_profile["submission"],
        b_profile["decision"]
    ]

    return random.choices(outcomes, weights=weights)[0]


def monte_carlo(a, b, runs=100000):

    results = {}

    for _ in range(runs):

        outcome = simulate_fight(a, b)

        if outcome not in results:
            results[outcome] = 0

        results[outcome] += 1

    # convert to percentages
    for k in results:
        results[k] = round(results[k] / runs * 100, 2)

    ranked = dict(sorted(results.items(), key=lambda x: x[1], reverse=True))

    return ranked


# -----------------------------
# API Routes
# -----------------------------

@app.route("/")
def home():

    return """
    <h1>UFC Fight Simulator</h1>

    <p>Example:</p>

    <a href="/simulate?fighter_a=Holloway&fighter_b=Oliveira">
    Simulate Holloway vs Oliveira
    </a>
    """


@app.route("/simulate")
def simulate():

    fighter_a = request.args.get("fighter_a")
    fighter_b = request.args.get("fighter_b")

    if fighter_a not in fighters or fighter_b not in fighters:
        return {"error": "fighter not found"}

    results = monte_carlo(fighter_a, fighter_b)

    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
