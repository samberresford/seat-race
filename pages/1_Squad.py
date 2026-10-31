import pandas as pd
import streamlit as st
from model import SQUAD_FILE, fit_learning, load_results, on_water_order, to_seconds

st.title("Squad")
st.caption("Who's in the squad, their side and their best 2k. Nobody types a technique score: "
           "the app learns that from seat racing.")

squad = pd.read_csv(SQUAD_FILE)
for column in ["name", "side", "best_2k", "coach_rank"]:
    if column not in squad:
        squad[column] = None

# ---- Edit the squad ------------------------------------------------------------
st.subheader("Athletes")
edited = st.data_editor(
    squad[["name", "side", "best_2k", "coach_rank"]],
    num_rows="dynamic", hide_index=True, width="stretch",
    column_config={
        "name": st.column_config.TextColumn("Name", required=True),
        "side": st.column_config.SelectboxColumn("Side", options=["S", "B"], required=True),
        "best_2k": st.column_config.TextColumn("Best 2k", help="Like 6:31.8", required=True),
        "coach_rank": st.column_config.NumberColumn("Your side rank (optional)", min_value=1, step=1),
    },
)

def problems(table):
    found = []
    for r in table.itertuples():
        try:
            secs = to_seconds(str(r.best_2k))
            if not 300 < secs < 600:
                raise ValueError
        except ValueError:
            found.append(f"{r.name}: 2k should look like 6:31.8")
    if table["name"].duplicated().any():
        found.append("Two athletes have the same name")
    return found

if st.button("Save squad", type="primary"):
    issues = problems(edited.dropna(subset=["name"]))
    if issues:
        for issue in issues:
            st.error(issue)
    else:
        edited.dropna(subset=["name"]).to_csv(SQUAD_FILE, index=False)
        st.success(f"Saved {len(edited.dropna(subset=['name']))} athletes.")

# ---- On-water order ------------------------------------------------------------
st.subheader("Order on the water")
results = load_results()
if not results.empty and "source" in results:
    results = results[results["source"] == "pieces"]
learned = fit_learning(results, squad) if not results.empty else None
st.write("Erg speed plus what seat racing has shown so far." if learned else
         "No seat racing yet, so this is the erg order. It updates as results come in.")
order = on_water_order(squad, learned)
col_s, col_b = st.columns(2)
for col, side, label in [(col_s, "S", "Stroke side"), (col_b, "B", "Bow side")]:
    with col:
        st.markdown(f"**{label}**")
        side_order = order[order["side"] == side].reset_index(drop=True)
        side_order.index += 1
        st.dataframe(side_order[["name", "best_2k", "boat_moving", "races"]].round(2).rename(
            columns={"boat_moving": "boat-moving"}))
