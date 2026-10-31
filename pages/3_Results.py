import os
import numpy as np
import pandas as pd
import streamlit as st

st.title("Results")

if not os.path.exists("seat_races.csv"):
    st.info("No results yet. Save a seat race on the calculator page first.")
    st.stop()

races = pd.read_csv("seat_races.csv")
if races.empty:
    st.info("No results yet. Save a seat race on the calculator page first.")
    st.stop()

# seconds per 500 m, so pieces of different lengths can be compared
races["per_500"] = races["difference"] * 500 / races["piece_length"]

st.subheader("Every race")
st.dataframe(races, hide_index=True)

# each race counts for both athletes: plus for A, minus for B
a_side = pd.DataFrame({"athlete": races["athlete_a"], "per_500": races["per_500"]})
b_side = pd.DataFrame({"athlete": races["athlete_b"], "per_500": -races["per_500"]})
both = pd.concat([a_side, b_side])

table = both.groupby("athlete")["per_500"].agg(races="count", average="mean").round(2)
table = table.sort_values("average", ascending=False)

st.subheader("Average margin per athlete")
st.write("Seconds per 500 m won (+) or lost (−), averaged over every race.")
st.dataframe(table)

# ---- Ratings from every race, direct and indirect ---------------------------
# Each race is one equation: rating[A] - rating[B] = margin per 500 m.
# Least squares finds the ratings that fit all the equations best,
# like a line of best fit through lab data.
names = sorted(set(races["athlete_a"]) | set(races["athlete_b"]))
pos = {name: i for i, name in enumerate(names)}
rows = []
for r in races.itertuples():
    row = np.zeros(len(names))
    row[pos[r.athlete_a]] = 1
    row[pos[r.athlete_b]] = -1
    rows.append(row)
ratings = np.linalg.lstsq(np.array(rows), races["per_500"].to_numpy(), rcond=None)[0]

def link(start, goal):
    """The chain of races connecting two athletes, or None if there isn't one."""
    paths = {start: [start]}
    queue = [start]
    while queue:
        person = queue.pop(0)
        for r in races.itertuples():
            for a, b in [(r.athlete_a, r.athlete_b), (r.athlete_b, r.athlete_a)]:
                if a == person and b not in paths:
                    paths[b] = paths[person] + [b]
                    queue.append(b)
    return paths.get(goal)

# ---- Head-to-head check ----------------------------------------------------
st.subheader("Head-to-head check")
st.write("Only a direct race between two athletes should decide a seat.")

c1, c2 = st.columns(2)
x = c1.selectbox("Athlete", names, key="h2h_x")
y = c2.selectbox("Against", names, index=min(1, len(names) - 1), key="h2h_y")
clear = st.slider("Clear margin (s per 500 m)", 0.1, 1.0, 0.5, 0.1)

# races where these two swapped with each other, in either order
x_was_a = (races["athlete_a"] == x) & (races["athlete_b"] == y)
y_was_a = (races["athlete_a"] == y) & (races["athlete_b"] == x)
margins = pd.concat([races.loc[x_was_a, "per_500"], -races.loc[y_was_a, "per_500"]])

if x == y:
    st.info("Pick two different athletes.")
elif len(margins) == 0:
    chain = link(x, y)
    if chain is None:
        st.error(f"No link between {x} and {y}: none of their results connect. Race them directly.")
    else:
        est = ratings[pos[x]] - ratings[pos[y]]
        ahead, behind = (x, y) if est > 0 else (y, x)
        st.warning(f"Indirect estimate only: {ahead} ahead of {behind} by about {abs(est):.2f} s per 500 m, "
                   f"worked out through {' → '.join(chain)}. They haven't raced each other, "
                   f"so race them before deciding a seat.")
else:
    avg = margins.mean()
    n = len(margins)
    if abs(avg) < clear:
        st.warning(f"Too close to call: {avg:+.2f} s per 500 m over {n} race(s). Re-race them.")
    else:
        winner, loser = (x, y) if avg > 0 else (y, x)
        st.success(f"{winner} beat {loser} directly by {abs(avg):.2f} s per 500 m over {n} race(s).")

# ---- Delete a result -------------------------------------------------------
st.subheader("Delete a result")
labels = [f"{r.date}: {r.athlete_a} v {r.athlete_b} ({r.difference:+.1f} s)" for r in races.itertuples()]
choice = st.selectbox("Pick the result to remove", range(len(races)), format_func=lambda i: labels[i])
sure = st.checkbox("Yes, delete this result")

if st.button("Delete", disabled=not sure):
    races = races.drop(index=choice)
    races.drop(columns="per_500").to_csv("seat_races.csv", index=False)
    st.rerun()
