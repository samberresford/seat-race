import math

import numpy as np
import pandas as pd
import streamlit as st
from model import BOATS, fit_learning, load_results, to_seconds
from storage import load_squad, require_password, save_json

require_password()

st.title("Selection")
st.caption("Who's in, who's out, how sure the evidence is, and which pieces would settle the rest.")

squad = load_squad()
if squad.empty:
    st.info("No athletes yet. Add your squad on the Squad page first.")
    st.stop()
split = dict(zip(squad["name"], squad["best_2k"].apply(to_seconds) / 4))
side_of = dict(zip(squad["name"], squad["side"]))

results = load_results()
if not results.empty and "source" in results:
    results = results[results["source"] == "pieces"]
learned = fit_learning(results, squad) if not results.empty else None

# ---- Everyone's estimated speed on the water, with how sure we are ------------
erg_weight = learned["erg_weight"] if learned else 1.0
known = learned["scores"].set_index("athlete") if learned else pd.DataFrame(columns=["boat_moving", "plus_minus", "races"])
UNRACED_SE = 1.5                       # how unsure we are about someone who hasn't seat raced

table = pd.DataFrame({"athlete": list(split)})
table["side"] = table["athlete"].map(side_of)
table["boat_moving"] = table["athlete"].map(known["boat_moving"]).fillna(0.0)
table["se"] = table["athlete"].map(known["plus_minus"] / 1.96).fillna(UNRACED_SE)
table["races"] = table["athlete"].map(known["races"]).fillna(0).astype(int)
table["on_water"] = -erg_weight * table["athlete"].map(split) + table["boat_moving"]

def chance_better(a, b):
    """Probability a is genuinely quicker on the water than b, given the evidence so far."""
    ra, rb = table.set_index("athlete").loc[a], table.set_index("athlete").loc[b]
    z = (ra["on_water"] - rb["on_water"]) / math.sqrt(ra["se"] ** 2 + rb["se"] ** 2)
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))

# direct head-to-heads, in seconds per 500 m (+ = first named athlete quicker)
direct = {}
if not results.empty:
    # ordinary swaps, plus the two strokes swapping boats (a fair test between those two)
    usable = ~results["stroke_swap"].astype(bool) | results.get("strokes_swapped", False)
    for r in results[usable].itertuples():
        direct.setdefault(frozenset((r.athlete_a, r.athlete_b)), []).append(
            (r.athlete_a, r.difference * 500 / r.piece_length))

def direct_margin(a, b):
    found = direct.get(frozenset((a, b)), [])
    if not found:
        return None, 0
    margins = [m if first == a else -m for first, m in found]
    return float(np.mean(margins)), len(margins)

# ---- Settings ------------------------------------------------------------------
c1, c2, c3 = st.columns(3)
select_for = c1.selectbox("Selecting for", list(BOATS.keys()))
sure_enough = c2.slider("Confidence needed", 0.70, 0.99, 0.90, 0.01,
                        help="How sure the evidence must be before a seat is called.")
clear = c3.slider("Clear direct margin (s/500)", 0.1, 1.0, 0.3, 0.1)
per_side = BOATS[select_for] // 2

if learned:
    st.write(f"Based on {learned['results_used']} seat race results. Ergs explain about "
             f"{learned['erg_share']:.0%} of the differences on the water so far.")
else:
    st.info("No seat racing results yet, so this is the erg order only. Every seat is undecided.")

needed = []                                     # pairs that would settle a seat
for side, label in [("S", "Stroke side"), ("B", "Bow side")]:
    st.subheader(label)
    group = table[table["side"] == side].sort_values("on_water", ascending=False).reset_index(drop=True)
    group["position"] = np.where(group.index < per_side, "In", "Out")
    st.dataframe(group[["athlete", "position", "boat_moving", "races"]].round(2).rename(
        columns={"boat_moving": "boat-moving (s/500)"}), hide_index=True)

    if len(group) <= per_side:
        st.write(f"Only {len(group)} athletes for {per_side} seats: everyone is in.")
        continue

    # the seat on the line: last one in against each of the first two out
    last_in = group.loc[per_side - 1, "athlete"]
    for k in range(per_side, min(per_side + 2, len(group))):
        first_out = group.loc[k, "athlete"]
        p = chance_better(last_in, first_out)
        margin, n = direct_margin(last_in, first_out)
        st.progress(min(p, 0.999), text=f"{last_in} over {first_out}: {p:.0%} sure")
        if margin is None:
            st.warning(f"Not decided: {last_in} and {first_out} have never raced each other directly.")
            needed.append((last_in, first_out))
        elif margin < 0:
            st.warning(f"Conflict: {first_out} won their direct race by {-margin:.2f} s/500, "
                       f"but other results put {last_in} ahead. Re-race them.")
            needed.append((last_in, first_out))
        elif margin < clear or p < sure_enough:
            st.warning(f"Too close: {last_in} leads {first_out} by {margin:.2f} s/500 directly "
                       f"over {n} race(s), {p:.0%} sure. Race again.")
            needed.append((last_in, first_out))
        else:
            st.success(f"Decided: {last_in} beat {first_out} directly by {margin:.2f} s/500 "
                       f"over {n} race(s), and the overall evidence is {p:.0%} sure.")

# ---- Surprising results --------------------------------------------------------
if learned:
    odd = learned["checked"][learned["checked"]["surprise"] > 2.5]
    if not odd.empty:
        st.subheader("Results that don't fit")
        st.write("These results disagree strongly with everything else. Check the timing, "
                 "or re-race: one bad piece shouldn't decide a seat.")
        st.dataframe(odd[["date", "pieces", "athlete_a", "athlete_b", "actual_per_500",
                          "expected_per_500"]].round(2), hide_index=True)

# ---- Pieces still needed -------------------------------------------------------
st.subheader("Pieces still needed")
if not needed:
    st.success("Every seat on the line is decided.")
else:
    for a, b in needed:
        st.write(f"- {a} v {b}")
    st.caption("If both athletes in a pair are your strokes, the plan races them by swapping the strokes between boats.")
    if st.button("Prioritise these in the next plan", type="primary"):
        save_json("must_race", [list(pair) for pair in needed])
        st.success("Saved. The Seat Racing plan will put these pairs in opposite boats and race them first.")
