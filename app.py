import csv
import os
from datetime import date
"""
Seat Race Calculator - step 1
Run with:  streamlit run app.py

A seat race: two boats race a piece, swap ONE athlete each, race again.
The change in margin between the two pieces is caused by the swap.
"""
import pandas as pd
import streamlit as st
from model import SQUAD_FILE

st.title("Seat Race Calculator")
st.caption("Two boats, two pieces, one swap. Margins in seconds.")

# ---- Inputs -------------------------------------------------------------
col1, col2 = st.columns(2)
names = sorted(pd.read_csv("SQUAD_FILE")["name"])
with col1:
    athlete_a = st.selectbox("Athlete A (starts in Boat 1)", names)
with col2:
    athlete_b = st.selectbox("Athlete B (starts in Boat 2)", names, index=1)

if athlete_a == athlete_b:
    st.warning("Pick two different athletes.")
    st.stop()

st.write("Enter margins from **Boat 1's point of view**: positive = Boat 1 won, negative = Boat 1 lost.")
m1 = st.number_input("Piece 1 margin (A in Boat 1)", value=0.0, step=0.1, format="%.1f")
m2 = st.number_input("Piece 2 margin (B in Boat 1, after the swap)", value=0.0, step=0.1, format="%.1f")
piece_length = st.number_input("Piece length (metres)", value=1000, step=250)

# ---- Calculation --------------------------------------------------------
# The swap changes BOTH boats, so the swing counts the A-vs-B difference twice.
swing = m1 - m2              # how much Boat 1's margin changed when A left it
difference = swing / 2       # A's advantage over B, in seconds over this piece
per_500 = difference * 500 / piece_length if piece_length else 0

# ---- Output -------------------------------------------------------------
st.subheader("Result")
if difference > 0:
    winner, loser = athlete_a, athlete_b
elif difference < 0:
    winner, loser = athlete_b, athlete_a
else:
    winner = loser = None

if winner:
    st.metric(f"{winner} beat {loser} by", f"{abs(difference):.1f} s",
              help=f"Margin swing {swing:+.1f} s, halved because the swap affects both boats.")
    st.write(f"That's about **{abs(per_500):.1f} s per 500 m**.")
else:
    st.write("Dead heat: no difference between the two athletes.")



if st.button("Save result"):
    file_exists = os.path.exists("seat_races.csv")
    with open("seat_races.csv", "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "athlete_a", "athlete_b", "m1", "m2", "piece_length", "difference"])
        writer.writerow([date.today(), athlete_a, athlete_b, m1, m2, piece_length, difference])
    st.success("Saved!")


