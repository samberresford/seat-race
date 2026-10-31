"""
Makes a pretend season of seat racing to test the learning model.
Each athlete gets a secret boat-moving score. If the app can find those
scores from the pretend results, we know the learning works.

Run once in Terminal:  python simulate_season.py
"""
import numpy as np
import pandas as pd
from model import to_seconds

rng = np.random.default_rng(42)
squad = pd.read_csv("sample_squad.csv")
squad["split"] = squad["best_2k"].apply(to_seconds) / 4

# the secret answers: seconds per 500 m each athlete is better (+) or worse (-) than their erg
squad["true_boat_moving"] = rng.normal(0, 1.5, len(squad)).round(2)
# and how much each one lifts a crew when they stroke (only matters for stroke-side athletes)
squad["true_stroke"] = np.where(squad["side"] == "S", rng.normal(0, 1.0, len(squad)), 0).round(2)
stroke_effect = dict(zip(squad["name"], squad["true_stroke"]))
ability = dict(zip(squad["name"], -squad["split"] + squad["true_boat_moving"]))

seats, piece_length, noise = 4, 1000, 0.5
rows = []
for session_no in range(1, 7):                     # 6 sessions of 6 pieces
    crews = {}
    for side in ["S", "B"]:
        people = list(rng.permutation(squad[squad["side"] == side]["name"]))[:4]
        crews[side] = [people[:2], people[2:]]     # 2 per side in each boat
    for piece in range(1, 7):
        if piece == 4:                             # the two strokes swap boats
            crews["S"][0][0], crews["S"][1][0] = crews["S"][1][0], crews["S"][0][0]
        elif piece > 1:                            # swap one same-side pair, not the strokes
            side = rng.choice(["S", "B"])
            i = 1 if side == "S" else rng.integers(0, 2)
            j = 1 if side == "S" else rng.integers(0, 2)
            crews[side][0][i], crews[side][1][j] = crews[side][1][j], crews[side][0][i]
        boat1 = [crews["S"][0][0], crews["B"][0][0], crews["S"][0][1], crews["B"][0][1]]
        boat2 = [crews["S"][1][0], crews["B"][1][0], crews["S"][1][1], crews["B"][1][1]]
        per_500 = (sum(ability[n] for n in boat1) + stroke_effect[boat1[0]]
                   - sum(ability[n] for n in boat2) - stroke_effect[boat2[0]]) / seats
        margin = per_500 * piece_length / 500 + rng.normal(0, noise)
        rows.append({"session": f"Sim {session_no}", "piece": piece, "boat_class": "4- / 4+",
                     "piece_length": piece_length, "boat1": "|".join(boat1),
                     "boat2": "|".join(boat2), "margin": round(margin, 1)})

pd.DataFrame(rows).to_csv("sim_pieces.csv", index=False)
squad[["name", "true_boat_moving", "true_stroke"]].to_csv("sim_truth.csv", index=False)
print(f"Made {len(rows)} pretend pieces in sim_pieces.csv")
