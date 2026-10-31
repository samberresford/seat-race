import streamlit as st
from model import BOATS, load_squad, tech_slider

st.title("Squad")

tech_impact = tech_slider()          # the slider now lives in the sidebar
squad = load_squad(tech_impact)      # all the maths is in model.py

# ---- Selection -------------------------------------------------------------
top_boat = st.selectbox("Top boat", list(BOATS.keys()))
per_side = BOATS[top_boat] // 2
width = st.slider("Borderline places either side of the cut", 1, 3, 1)

def status(side_rank):
    if side_rank <= per_side - width:
        return "In"
    elif side_rank <= per_side + width:
        return "Borderline"
    else:
        return "Out"

squad["status"] = squad["side_rank"].apply(status)

st.write(f"{top_boat}: {per_side} seats per side")
col_s, col_b = st.columns(2)
for col, side, label in [(col_s, "S", "Stroke side"), (col_b, "B", "Bow side")]:
    with col:
        st.subheader(label)
        side_df = squad[squad["side"] == side].sort_values("side_rank")
        st.dataframe(side_df[["side_rank", "name", "adjusted_2k", "status"]], hide_index=True)

# ---- Your order vs the model -------------------------------------------------
# positive gap = you rank them HIGHER than the model does
st.subheader("Your order vs the model")
compare = squad.sort_values("gap", key=abs, ascending=False)
st.dataframe(compare[["name", "side", "coach_rank", "side_rank", "gap"]], hide_index=True)
st.write(f"Average gap: **{squad['gap'].abs().mean():.1f} places**. "
         "Move the tech slider to see when the model agrees with you most.")

# ---- Full ranking ----------------------------------------------------------
st.subheader("Full ranking")
st.write(f"{len(squad)} athletes")
st.dataframe(squad[["rank", "name", "side", "best_2k", "tech_score", "watts", "boat_watts",
                    "adjusted_2k", "status"]].round(0), hide_index=True)
