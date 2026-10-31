import os

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Seat Racing", page_icon="🚣")
st.title("Seat Racing")
st.write("Plan seat races, record results on the launch, and let the evidence pick the crews.")

st.subheader("How it works")
st.markdown(
    "1. **Squad:** add athletes with their side and best 2k.\n"
    "2. **Plan:** pick who's racing and the strokes. The app builds even crews and chooses the swaps "
    "a coach would want, in an order nobody can predict. Save the plan.\n"
    "3. **Enter Piece:** on the launch, type each piece's margin (or both boats' times). "
    "The app spots every swap.\n"
    "4. **Selection:** who's in, how sure the evidence is, and which pieces would settle the rest. "
    "Send those back to the plan.\n"
    "5. **Results** and **Learning:** every head-to-head, and what the app has learned: how much ergs "
    "explain, each athlete's boat-moving score, and each stroke's effect."
)

pieces = pd.read_csv("pieces.csv") if os.path.exists("pieces.csv") else pd.DataFrame()
c1, c2 = st.columns(2)
c1.metric("Pieces recorded", len(pieces))
c2.metric("Sessions", pieces["session"].nunique() if not pieces.empty else 0)

# ---- Quick calculator (nothing is saved) ---------------------------------------
with st.expander("Quick calculator: one swap, worked out by hand"):
    st.write("Margins from Boat 1's point of view: positive = Boat 1 ahead.")
    m1 = st.number_input("Piece 1 margin (A in Boat 1)", value=0.0, step=0.1, format="%.1f")
    m2 = st.number_input("Piece 2 margin (B in Boat 1, after the swap)", value=0.0, step=0.1, format="%.1f")
    length = st.number_input("Piece length (m)", 250, 2000, 1000, 250)
    difference = (m1 - m2) / 2          # the swap changes both boats, so halve the swing
    if difference:
        st.metric(f"Athlete {'A' if difference > 0 else 'B'} quicker by", f"{abs(difference):.1f} s",
                  f"{abs(difference) * 500 / length:.2f} s per 500 m", delta_color="off")
    else:
        st.write("Dead heat.")
