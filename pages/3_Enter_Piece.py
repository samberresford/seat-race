from datetime import date

import pandas as pd
import streamlit as st
from model import head_to_heads
from storage import load_json, load_pieces, load_squad, require_password, save_pieces

require_password()

st.title("Enter a piece")

squad = load_squad()
if squad.empty:
    st.info("No athletes yet. Add your squad on the Squad page first.")
    st.stop()
SEATS = {"8+": 8, "4- / 4+": 4, "2-": 2}
pieces_so_far = load_pieces()

def recorded(session):
    """Piece numbers already saved for a session."""
    return set(pieces_so_far.loc[pieces_so_far["session"] == session, "piece"].dropna().astype(int))

def save_piece(session, boat_class, piece_length, boat1, boat2, margin, lane1, conditions, piece_no=None):
    if piece_no is None:                                   # by hand: the next number after the last one
        piece_no = max(recorded(session), default=0) + 1
    row = pd.DataFrame([{
        "session": session, "piece": piece_no, "boat_class": boat_class,
        "piece_length": piece_length, "boat1": "|".join(boat1),
        "boat2": "|".join(boat2), "margin": round(margin, 1),
        "lane1": lane1, "conditions": conditions,
    }])
    everything = pd.concat([pieces_so_far, row], ignore_index=True).sort_values(["session", "piece"], kind="stable")
    save_pieces(everything)
    return piece_no

def lane_and_conditions(session, key):
    """Boats keep their lanes all session; a change means those two pieces aren't compared."""
    earlier = pieces_so_far[pieces_so_far["session"] == session]
    last_lane = earlier["lane1"].dropna().iloc[-1] if "lane1" in earlier and earlier["lane1"].notna().any() else "Lane A"
    c1, c2 = st.columns(2)
    lane1 = c1.radio("Boat 1 is in", ["Lane A", "Lane B"], index=["Lane A", "Lane B"].index(last_lane),
                     horizontal=True, key=f"lane{key}")
    conditions = c2.text_input("Conditions (optional)", placeholder="e.g. headwind, choppy", key=f"cond{key}")
    if not earlier.empty and lane1 != last_lane:
        st.warning("Boats have changed lanes, so this piece won't be compared with the one before.")
    return lane1, conditions

def to_seconds(text):
    """'3:21.4' or '201.4' -> 201.4 seconds"""
    text = text.strip().replace(",", ".")
    if ":" in text:
        mins, secs = text.split(":")
        return int(mins) * 60 + float(secs)
    return float(text)

def margin_input(key):
    """Margin typed directly, or worked out from both boats' times."""
    how = st.radio("Enter the result as", ["Margin", "Each boat's time"], horizontal=True, key=f"how{key}")
    if how == "Margin":
        return st.number_input("Margin (s): positive = Boat 1 ahead, negative = Boat 2 ahead",
                               value=0.0, step=0.1, format="%.1f", key=f"m{key}")
    t1, t2 = st.columns(2)
    time1 = t1.text_input("Boat 1 time", placeholder="3:21.4", key=f"t1{key}")
    time2 = t2.text_input("Boat 2 time", placeholder="3:22.6", key=f"t2{key}")
    try:
        margin = to_seconds(time2) - to_seconds(time1)
        st.write(f"Margin: Boat {'1' if margin >= 0 else '2'} ahead by {abs(margin):.1f} s")
        return margin
    except ValueError:
        st.write("Type both times, e.g. 3:21.4")
        return None

# ---- From the saved plan ------------------------------------------------------
plan = load_json("saved_plan")

mode = st.radio("How are you entering this?", ["From the saved plan", "Crews by hand"],
                horizontal=True, index=0 if plan else 1, disabled=plan is None)

if mode == "From the saved plan" and plan:
    names = [s["name"] for s in plan["sessions"]]
    session = st.selectbox("Session", names)
    planned = plan["sessions"][names.index(session)]["pieces"]
    # the next planned piece that hasn't been saved (so a deleted piece can be re-recorded)
    missing = [k for k in range(1, len(planned) + 1) if k not in recorded(session)]

    if not missing:
        st.success(f"All {len(planned)} pieces of {session} are recorded.")
    else:
        number = missing[0]
        p = planned[number - 1]
        st.subheader(f"Piece {number} of {len(planned)}: {p['swap']}")
        seat_names = ["Stroke"] + [str(k) for k in range(len(p["boat1"]) - 1, 1, -1)] + ["Bow"]
        st.table(pd.DataFrame({"Seat": seat_names[:len(p["boat1"])], "Boat 1": p["boat1"], "Boat 2": p["boat2"]}))
        margin = margin_input("plan")
        lane1, conditions = lane_and_conditions(session, "plan")
        if st.button("Save piece", type="primary", disabled=margin is None):
            n = save_piece(session, plan["boat_class"], plan["piece_length"], p["boat1"], p["boat2"],
                           margin, lane1, conditions, piece_no=number)
            st.toast(f"Saved piece {n}")
            st.rerun()
        st.caption("Crews changed on the water? Switch to 'Crews by hand' for this piece.")

# ---- By hand ------------------------------------------------------------------
else:
    c1, c2, c3 = st.columns(3)
    session = c1.text_input("Session", str(date.today()))
    boat_class = c2.selectbox("Boat", list(SEATS.keys()), index=1)
    piece_length = c3.number_input("Piece (m)", 250, 2000, 1000, 250)
    n = SEATS[boat_class]

    def crew_picker(boat, start):
        st.subheader(f"Boat {boat}")
        crew = []
        for seat in range(n, 0, -1):
            side = "S" if seat % 2 == 0 else "B"
            label = "Stroke" if seat == n else ("Bow" if seat == 1 else f"Seat {seat}")
            options = squad[squad["side"] == side]["name"].tolist()
            crew.append(st.selectbox(f"{label} ({side})", options,
                                     index=(start + (seat - 1) // 2) % len(options),
                                     key=f"{boat_class}-b{boat}s{seat}"))
        return crew

    col1, col2 = st.columns(2)
    with col1:
        boat1 = crew_picker(1, 0)
    with col2:
        boat2 = crew_picker(2, n // 2)

    margin = margin_input("hand")
    lane1, conditions = lane_and_conditions(session, "hand")
    everyone = boat1 + boat2
    if len(set(everyone)) < len(everyone):
        st.warning("Someone is in more than one seat. Each athlete can only row once per piece.")
    elif st.button("Save piece", type="primary", disabled=margin is None):
        k = save_piece(session, boat_class, piece_length, boat1, boat2, margin, lane1, conditions)
        st.toast(f"Saved piece {k} of {session}")
        st.rerun()

# ---- This session so far --------------------------------------------------
this_session = pieces_so_far[pieces_so_far["session"] == session]
if not this_session.empty:
    st.subheader(f"{session} so far")
    st.dataframe(this_session, hide_index=True)

    swaps = head_to_heads(this_session)
    st.subheader("Swaps found")
    if swaps.empty:
        st.write("None yet. A result counts when exactly one athlete swaps between pieces.")
    else:
        for r in swaps.itertuples():
            winner, loser = (r.athlete_a, r.athlete_b) if r.difference > 0 else (r.athlete_b, r.athlete_a)
            note = (" (boats changed lanes, not used)" if r.lanes_changed else
                    " (strokes swapped boats)" if r.strokes_swapped else
                    " (stroke change, not used)" if r.stroke_swap else "")
            st.write(f"Pieces {r.pieces}: {winner} beat {loser} by {abs(r.difference):.1f} s{note}")

# ---- Delete one piece (only one at a time, and only after you've checked it) ------------
if not pieces_so_far.empty:
    with st.expander("Delete a piece entered by mistake"):
        sessions = list(pieces_so_far["session"].unique())
        which_session = st.selectbox("Session", sessions, key="del_session")
        options = pieces_so_far[pieces_so_far["session"] == which_session]
        which = st.selectbox("Piece", options.index, key="del_piece",
                             format_func=lambda i: f"Piece {int(options.loc[i, 'piece'])}: margin {options.loc[i, 'margin']:+.1f} s")
        chosen = options.loc[which]
        st.write(f"Boat 1: {chosen['boat1'].replace('|', ', ')}  \nBoat 2: {chosen['boat2'].replace('|', ', ')}")
        sure = st.checkbox(f"Yes, delete piece {int(chosen['piece'])} of {which_session}. This can't be undone.",
                           key="del_sure")
        if st.button("Delete this piece", disabled=not sure):
            save_pieces(pieces_so_far.drop(index=which))
            st.session_state.pop("del_sure", None)
            st.toast("Piece deleted")
            st.rerun()
