"""
Shared seat racing maths, used by every page.
Keeping it in one file means every page ranks athletes the same way.
"""
import os

import numpy as np
import pandas as pd

# the real squad stays private; anyone else gets the made-up sample squad
SQUAD_FILE = "squad.csv" if os.path.exists("squad.csv") else "sample_squad.csv"

# seats in each boat class
BOATS = {"8+": 8, "4- / 4+": 4, "2-": 2}

# rough club men's boat speeds in metres per second (about a 6:00 8+, 6:40 4-, 7:20 2-)
# only used to turn a power gap into a predicted margin in seconds
BOAT_SPEED = {"8+": 5.6, "4- / 4+": 5.0, "2-": 4.5}


# turn "6:31.8" into seconds (391.8)
def to_seconds(t):
    mins, secs = t.split(":")
    return int(mins) * 60 + float(secs)


# turn seconds back into "6:31.8"
def to_time(s):
    return f"{int(s // 60)}:{s % 60:04.1f}"


# short name for diagrams: "Elliott Lynch Warden" -> "Elliott L"
def short_name(name):
    parts = name.split()
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[1][0]}"


def on_water_order(squad, learned):
    """Everyone's estimated speed on the water (s/500 for one rower, bigger = faster):
    erg speed scaled by what's been learned, plus their boat-moving score (0 until raced)."""
    erg_weight = learned["erg_weight"] if learned else 1.0
    known = learned["scores"].set_index("athlete") if learned else None
    table = squad[["name", "side", "best_2k"]].copy()
    table["boat_moving"] = table["name"].map(known["boat_moving"]).fillna(0.0) if known is not None else 0.0
    table["plus_minus"] = table["name"].map(known["plus_minus"]).fillna(2.9) if known is not None else 2.9
    table["races"] = table["name"].map(known["races"]).fillna(0).astype(int) if known is not None else 0
    table["on_water"] = -erg_weight * table["best_2k"].apply(to_seconds) / 4 + table["boat_moving"]
    return table.sort_values("on_water", ascending=False)


def lanes_differ(lane_before, lane_after):
    """True only when both pieces recorded a lane and they're different."""
    known = [lane for lane in (lane_before, lane_after) if isinstance(lane, str) and lane]
    return len(known) == 2 and known[0] != known[1]


def head_to_heads(pieces):
    """Turn consecutive pieces into seat race results.
    A result only counts when exactly one athlete left Boat 1 and one joined it."""
    rows = []
    for session, group in pieces.groupby("session", sort=False):
        group = group.sort_values("piece")
        previous = None
        for current in group.itertuples():
            if previous is not None and current.boat_class == previous.boat_class \
                    and current.piece_length == previous.piece_length:
                before = previous.boat1.split("|")
                after = current.boat1.split("|")
                before2 = previous.boat2.split("|")
                after2 = current.boat2.split("|")
                left = [name for name in before if name not in after]
                joined = [name for name in after if name not in before]
                if len(left) == 1 and len(joined) == 1:
                    rows.append({
                        "date": session,
                        "athlete_a": left[0],      # was in Boat 1 for the first piece
                        "athlete_b": joined[0],    # moved into Boat 1 for the second
                        "m1": previous.margin,
                        "m2": current.margin,
                        "piece_length": current.piece_length,
                        "boat_class": current.boat_class,
                        "difference": (previous.margin - current.margin) / 2,
                        "stroke_swap": before[0] != after[0],
                        # the two strokes swapped boats and both kept stroking: this measures stroking
                        "strokes_swapped": before[0] == after2[0] and after[0] == before2[0] and before[0] != after[0],
                        "pieces": f"{previous.piece}-{current.piece}",
                        # boats must keep their lanes between the two pieces, or lane bias creeps in
                        "lanes_changed": lanes_differ(getattr(previous, "lane1", None), getattr(current, "lane1", None)),
                    })
            previous = current
    return pd.DataFrame(rows)


def load_results():
    """Every seat race result: from the Enter Piece page and from the calculator."""
    parts = []
    if os.path.exists("pieces.csv"):
        found = head_to_heads(pd.read_csv("pieces.csv"))
        if not found.empty:
            found = found[~found["lanes_changed"]]
            found["source"] = "pieces"
            parts.append(found)
    if os.path.exists("seat_races.csv"):
        calc = pd.read_csv("seat_races.csv")
        if not calc.empty:
            calc["source"] = "calculator"
            calc["stroke_swap"] = False
            parts.append(calc)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def fit_learning(results, squad, tech_spread=1.5, stroke_spread=1.0, noise=0.5):
    """Learn from seat race results how much each athlete moves a boat beyond their erg,
    and how much each stroke lifts a crew.

    Every result says: (A's ability - B's ability) on the water.
    Ability = erg_weight x erg speed + boat-moving score.
    When the two strokes swap boats, the result also includes A's stroke effect - B's.
    Scores start at 0 and only move away when results back it up.
    All numbers are in seconds per 500 m for one rower, so 8s, 4s and 2s compare.
    """
    split = dict(zip(squad["name"], squad["best_2k"].apply(to_seconds) / 4))
    use = results[results["athlete_a"].isin(split) & results["athlete_b"].isin(split)].copy()
    if "strokes_swapped" not in use:
        use["strokes_swapped"] = False
    use["strokes_swapped"] = use["strokes_swapped"].fillna(False).astype(bool)
    # keep ordinary swaps and clean stroke-for-stroke swaps; anything messier can't be untangled
    use = use[~use["stroke_swap"].astype(bool) | use["strokes_swapped"]]
    if use.empty:
        return None

    names = sorted(set(use["athlete_a"]) | set(use["athlete_b"]))
    strokes = sorted(set(use.loc[use["strokes_swapped"], "athlete_a"]) | set(use.loc[use["strokes_swapped"], "athlete_b"]))
    pos = {name: i + 1 for i, name in enumerate(names)}                   # column 0 is the erg weight
    spos = {name: len(names) + 1 + i for i, name in enumerate(strokes)}   # then the stroke effects
    seats = use["boat_class"].map(BOATS).fillna(4).to_numpy()

    X = np.zeros((len(use), 1 + len(names) + len(strokes)))
    for row, r in enumerate(use.itertuples()):
        X[row, 0] = split[r.athlete_b] - split[r.athlete_a]  # + when A is quicker on the erg
        X[row, pos[r.athlete_a]] = 1
        X[row, pos[r.athlete_b]] = -1
        if r.strokes_swapped:
            X[row, spos[r.athlete_a]] = 1
            X[row, spos[r.athlete_b]] = -1
    y = (use["difference"] * 500 / use["piece_length"]).to_numpy() * seats

    # noise in a boat margin is about the same in any boat, so one rower's share is bigger in an 8
    def solve(noise):
        w = 1 / (noise * seats) ** 2
        prior = np.diag([1 / 0.5 ** 2] + [1 / tech_spread ** 2] * len(names) + [1 / stroke_spread ** 2] * len(strokes))
        prior_mean = np.zeros(X.shape[1])
        prior_mean[0] = 1.0                                  # start by trusting ergs fully
        A = X.T @ (X * w[:, None]) + prior
        b = X.T @ (w * y) + prior @ prior_mean
        cov = np.linalg.inv(A)
        return cov @ b, cov

    coef, cov = solve(noise)
    if len(use) >= 10:                                       # enough data to measure the noise
        resid = (y - X @ coef) / seats
        noise = max(0.1, float(np.sqrt(np.mean(resid ** 2) * len(use) / max(len(use) - X.shape[1] / 2, 1))))
        coef, cov = solve(noise)

    se = np.sqrt(np.diag(cov))
    races = lambda n: int(((use["athlete_a"] == n) | (use["athlete_b"] == n)).sum())
    scores = pd.DataFrame({
        "athlete": names,
        "boat_moving": coef[1:len(names) + 1],
        "plus_minus": 1.96 * se[1:len(names) + 1],
        "races": [races(n) for n in names],
    }).sort_values("boat_moving", ascending=False)
    stroke_scores = pd.DataFrame({
        "athlete": strokes,
        "stroke_effect": coef[len(names) + 1:],
        "plus_minus": 1.96 * se[len(names) + 1:],
    }).sort_values("stroke_effect", ascending=False)

    # how surprising each result is, given everything else: big surprises are worth re-racing
    checked = use.copy()
    checked["expected_per_500"] = (X @ coef) / seats
    checked["actual_per_500"] = y / seats
    checked["surprise"] = (checked["actual_per_500"] - checked["expected_per_500"]).abs() / noise

    erg_part = np.var([coef[0] * -split[n] for n in names])
    tech_part = np.var(coef[1:len(names) + 1])
    return {
        "erg_weight": coef[0], "erg_weight_pm": 1.96 * se[0],
        "erg_share": erg_part / (erg_part + tech_part) if erg_part + tech_part else 1.0,
        "noise": noise, "results_used": len(use), "scores": scores, "strokes": stroke_scores,
        "checked": checked,
    }
