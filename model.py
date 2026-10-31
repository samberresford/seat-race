"""
Shared squad maths, used by every page.
Keeping it in one file means the Squad page and the Seat Racing page
always rank athletes the same way.
"""
import os

import pandas as pd
import streamlit as st

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


def tech_slider():
    """One tech slider in the sidebar, shared by every page."""
    if "tech_impact" not in st.session_state:
        st.session_state.tech_impact = 0.30
    st.session_state._tech = st.session_state.tech_impact

    def remember():
        st.session_state.tech_impact = st.session_state._tech

    st.sidebar.slider(
        "How much tech matters", 0.0, 1.0, step=0.05, key="_tech", on_change=remember,
        help="Share of power a tech-0 athlete loses. 0 = pure erg ranking.",
    )
    return st.session_state.tech_impact


def load_squad(tech_impact):
    """Read squad.csv and work out everyone's tech-adjusted power and rank."""
    squad = pd.read_csv(SQUAD_FILE)
    squad["2k_seconds"] = squad["best_2k"].apply(to_seconds)
    squad["watts"] = 2.80 / (squad["2k_seconds"] / 2000) ** 3

    # poor technique wastes power: tech 100 keeps it all, lower tech loses some
    squad["efficiency"] = 1 - tech_impact * (100 - squad["tech_score"]) / 100
    squad["boat_watts"] = squad["watts"] * squad["efficiency"]
    squad["adjusted_2k"] = (2000 * (2.80 / squad["boat_watts"]) ** (1 / 3)).apply(to_time)

    squad = squad.sort_values("boat_watts", ascending=False)
    squad["rank"] = range(1, len(squad) + 1)
    squad["side_rank"] = squad.groupby("side")["boat_watts"].rank(ascending=False, method="first").astype(int)
    if "coach_rank" in squad.columns:
        squad["gap"] = squad["side_rank"] - squad["coach_rank"]
    else:
        squad["gap"] = 0
    return squad
