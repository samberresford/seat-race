import os

import numpy as np
import pandas as pd
import streamlit as st
from model import SQUAD_FILE, fit_learning, head_to_heads, load_results

st.title("What the app has learned")

test_mode = st.toggle("Use the pretend test season", value=not os.path.exists("pieces.csv"))

if test_mode:
    if not os.path.exists("sim_pieces.csv"):
        st.info("No test season yet. In Terminal run:  python simulate_season.py")
        st.stop()
    results = head_to_heads(pd.read_csv("sim_pieces.csv"))
    squad = pd.read_csv("sample_squad.csv")
else:
    results = load_results()
    squad = pd.read_csv(SQUAD_FILE)
    if not results.empty and "boat_class" in results:
        results = results[results["source"] == "pieces"]   # calculator results don't record the boat

if results.empty:
    st.info("No results to learn from yet. Enter some pieces first.")
    st.stop()

out = fit_learning(results, squad)
if out is None:
    st.info("None of the results match athletes in the squad file.")
    st.stop()

# ---- Headline numbers --------------------------------------------------------
c1, c2, c3 = st.columns(3)
c1.metric("Results learned from", out["results_used"])
c2.metric("Erg explains", f"{out['erg_share']:.0%}", help="Share of the differences between athletes "
          "on the water that their ergs account for. The rest is boat-moving: technique, rhythm, skill.")
c3.metric("Noise per result", f"±{out['noise']:.2f} s/500", help="How much a single result wobbles. "
          "Measured from the data once there are 10+ results.")

if out["results_used"] < 15:
    st.warning("Early days: with fewer than about 15 results the scores lean heavily on ergs.")

# ---- Boat-moving scores --------------------------------------------------------
st.subheader("Boat-moving scores")
st.write("Seconds per 500 m each athlete moves a boat better (+) or worse (−) than their erg predicts. "
         "Everyone starts at 0 and only moves when results back it up. The ± is a 95% range.")
scores = out["scores"].copy()
scores["clear"] = np.where(scores["boat_moving"].abs() > scores["plus_minus"], "yes", "not yet")

if test_mode and os.path.exists("sim_truth.csv"):
    truth = pd.read_csv("sim_truth.csv").rename(columns={"name": "athlete"})
    scores = scores.merge(truth, on="athlete", how="left")
    found = np.corrcoef(scores["boat_moving"], scores["true_boat_moving"])[0, 1]
    st.success(f"Test check: the app's scores match the hidden true scores with a correlation of "
               f"{found:.2f} (1.00 = perfect).")

st.dataframe(scores.round(2), hide_index=True)

# ---- Stroke effects ------------------------------------------------------------
st.subheader("Stroke effects")
strokes = out["strokes"].copy()
if strokes.empty:
    st.write("No stroke swaps yet. Swap the two strokes between boats in a session to measure this.")
else:
    st.write("Seconds per 500 m each stroke lifts (+) or drags (−) a crew compared with their boat-moving "
             "score alone. Needs several stroke swaps before the ranges get narrow.")
    if test_mode and os.path.exists("sim_truth.csv"):
        strokes = strokes.merge(truth[["athlete", "true_stroke"]], on="athlete", how="left")
    st.dataframe(strokes.round(2), hide_index=True)
