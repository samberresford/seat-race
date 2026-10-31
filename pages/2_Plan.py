import base64
from itertools import combinations

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
from model import BOATS, fit_learning, load_results, short_name, to_seconds
from storage import load_json, load_squad, require_password, save_json

require_password()

st.title("Plan")
st.caption("Plans the swaps a coach would want: close calls, unanswered questions and people who "
           "haven't raced much, picked with some randomness so nobody can predict the next swap.")

squad = load_squad()
if squad.empty:
    st.info("No athletes yet. Add your squad on the Squad page first.")
    st.stop()
split = dict(zip(squad["name"], squad["best_2k"].apply(to_seconds) / 4))

# ---- What we know so far -----------------------------------------------------
# ability = how quick someone is on the water, in s/500 for one rower (bigger = faster).
# Before any results it's just the erg; the learning model adds each athlete's boat-moving score.
results = load_results()
if not results.empty:
    results = results[results["source"] == "pieces"] if "source" in results else results
learned = fit_learning(results, squad) if not results.empty else None
erg_weight = learned["erg_weight"] if learned else 1.0
boat_moving = dict(zip(learned["scores"]["athlete"], learned["scores"]["boat_moving"])) if learned else {}
unsure = dict(zip(learned["scores"]["athlete"], learned["scores"]["plus_minus"])) if learned else {}
ability = {n: -erg_weight * split[n] + boat_moving.get(n, 0.0) for n in split}
uncertainty = {n: unsure.get(n, 3.0) for n in split}
stroke_eff = dict(zip(learned["strokes"]["athlete"], learned["strokes"]["stroke_effect"])) if learned else {}
stroke_unsure = dict(zip(learned["strokes"]["athlete"], learned["strokes"]["plus_minus"])) if learned else {}

# head-to-heads already raced, and whether each one was clear
direct = {}
stroke_pairs = set()                    # pairs of strokes that have already swapped boats
if not results.empty:
    for r in results.itertuples():
        if not r.stroke_swap:
            key = frozenset((r.athlete_a, r.athlete_b))
            direct.setdefault(key, []).append(r.difference * 500 / r.piece_length)
        elif getattr(r, "strokes_swapped", False):
            stroke_pairs.add(frozenset((r.athlete_a, r.athlete_b)))

# pairs the Selection page asked for: race these first
must_race = {frozenset(pair) for pair in (load_json("must_race") or [])}

def answered(a, b, clear=0.5):
    margins = direct.get(frozenset((a, b)), [])
    return bool(margins) and abs(np.mean(margins)) >= clear

# ---- Settings ----------------------------------------------------------------
c1, c2, c3 = st.columns(3)
select_for = c1.selectbox("Selecting for", list(BOATS.keys()))
race_in = c2.selectbox("Racing in", list(BOATS.keys()), index=1)
piece_m = c3.number_input("Piece (m)", 500, 2000, 1000, 250)

per_side_cut = BOATS[select_for] // 2
need = BOATS[race_in]
seats = BOATS[race_in]

side_rank = {}
for side in "SB":
    ordered = sorted([n for n in split if squad.set_index("name").loc[n, "side"] == side],
                     key=lambda n: ability[n], reverse=True)
    side_rank.update({n: i + 1 for i, n in enumerate(ordered)})
coach_rank = dict(zip(squad["name"], squad["coach_rank"])) if "coach_rank" in squad else {}

def cut_distance(n):
    """How close someone is to the selection cut (0 = right on it)."""
    blended = (side_rank[n] + coach_rank.get(n, side_rank[n])) / 2
    return abs(blended - (per_side_cut + 0.5))

# ---- Who's racing ------------------------------------------------------------
racers = {}
with st.expander(f"Who's racing ({need} per side)", expanded=True):
    col_s, col_b = st.columns(2)
    for col, side, label in [(col_s, "S", "Stroke side"), (col_b, "B", "Bow side")]:
        options = sorted(squad[squad["side"] == side]["name"], key=lambda n: side_rank[n])
        default = sorted(options, key=cut_distance)[:need]
        racers[side] = col.multiselect(label, options, default=default)

for side, label in [("S", "stroke side"), ("B", "bow side")]:
    if len(racers[side]) != need:
        st.warning(f"Pick exactly {need} on {label} (you have {len(racers[side])}).")
        st.stop()

# the two strokes only ever swap with each other, so both boats always have one of them stroking
s1, s2 = st.columns(2)
stroke1 = s1.selectbox("Stroke, Boat 1", racers["S"], index=0)
stroke2 = s2.selectbox("Stroke, Boat 2", [n for n in racers["S"] if n != stroke1], index=0)
stroke_swaps = st.checkbox("Include a stroke swap in each session (the two strokes swap boats)", value=True,
                           help="Measures how much each stroke lifts a crew. Kept to one per session.")

# ---- Sessions ----------------------------------------------------------------
max_per_session = max(3, min(6, round(5000 / piece_m)))
swappable = {"S": [n for n in racers["S"] if n not in (stroke1, stroke2)], "B": racers["B"]}
possible = sum((need // 2 - (1 if side == "S" else 0)) ** 2 for side in "SB")   # swaps available per session
st.subheader("Sessions")
g1, g2 = st.columns(2)
per_session = g1.number_input("Pieces per session", 2, 8, max_per_session,
                              help=f"About 5 km of racing at {piece_m} m keeps fatigue from skewing the later pieces.")
n_sessions = g2.number_input("Sessions", 1, 6, 2)

if "plan_seed" not in st.session_state:
    st.session_state.plan_seed = 1
if st.button("New plan (reshuffle)"):
    st.session_state.plan_seed += 1
rng = np.random.default_rng(st.session_state.plan_seed)

# ---- Building the plan ---------------------------------------------------------
def copy_crews(c):
    return {b: {s: list(c[b][s]) for s in "SB"} for b in (1, 2)}

def boat_ability(boat):
    return sum(ability[n] for side in "SB" for n in boat[side]) + stroke_eff.get(boat["S"][0], 0.0)

def predicted_margin(c):
    """Boat 1's predicted lead in seconds over the piece."""
    return (boat_ability(c[1]) - boat_ability(c[2])) / seats * piece_m / 500

def pick(options, weights, temperature=1.0):
    """Choose among good options at random, favouring the better ones (not always the best)."""
    w = np.exp((np.array(weights) - max(weights)) / temperature)
    return options[rng.choice(len(options), p=w / w.sum())]

def swap_value(a, b, raced_today, count):
    """How much a coach would want this swap: close calls, unanswered questions,
    people near the cut, people the app is unsure about, and people who haven't raced much."""
    if frozenset((a, b)) in raced_today:
        return None
    value = 0.0
    value += 3.0 if not answered(a, b) else 0.0                 # question not yet answered
    value += 5.0 if frozenset((a, b)) in must_race else 0.0      # Selection page asked for this
    value -= 1.0 * abs(ability[a] - ability[b])                  # close calls tell you the most
    value -= 0.7 * (cut_distance(a) + cut_distance(b))          # seats being decided
    value += 0.5 * (uncertainty[a] + uncertainty[b])            # athletes the app knows least about
    value -= 1.5 * (count[a] + count[b])                         # spread the racing fairly
    return value

def setup_session(raced_today):
    """Fresh crews: strokes fixed, people who still need racing put in opposite boats,
    boats roughly even, and a random pick among the good options."""
    options, scores = [], []
    rest_s = [n for n in racers["S"] if n not in (stroke1, stroke2)]
    for s_half in combinations(rest_s, need // 2 - 1):
        for b_half in combinations(racers["B"], need // 2):
            c = {1: {"S": [stroke1] + list(s_half), "B": list(b_half)},
                 2: {"S": [stroke2] + [n for n in rest_s if n not in s_half],
                     "B": [n for n in racers["B"] if n not in b_half]}}
            fresh = sum((3 if frozenset((a, b)) in must_race else 1)
                        * (not answered(a, b) and frozenset((a, b)) not in raced_today)
                        for side in "SB" for a in c[1][side] for b in c[2][side]
                        if a not in (stroke1, stroke2) and b not in (stroke1, stroke2))
            balance = abs(boat_ability(c[1]) - boat_ability(c[2])) / seats
            options.append(c)
            scores.append(2.0 * fresh - 4.0 * balance)
    return copy_crews(pick(options, scores, temperature=1.5))

count = {n: 0 for side in "SB" for n in racers[side]}
raced_today = set()
sessions = []
for _ in range(int(n_sessions)):
    current = setup_session(raced_today)
    pieces = [{"crews": copy_crews(current), "swap": None}]          # baseline piece
    stroke_done = not stroke_swaps
    stroke_at = int(rng.integers(2, per_session + 1))               # which piece gets the stroke swap
    while len(pieces) < per_session:
        candidates, values = [], []
        for side in "SB":
            for i, a in enumerate(current[1][side]):
                for j, b in enumerate(current[2][side]):
                    if a in (stroke1, stroke2) or b in (stroke1, stroke2):
                        continue                                       # never swap the strokes
                    v = swap_value(a, b, raced_today, count)
                    if v is not None:
                        candidates.append((side, i, j, a, b))
                        values.append(v)
        # the strokes swap boats once a session, on a randomly chosen piece so it can't be predicted
        a0, b0 = current[1]["S"][0], current[2]["S"][0]
        if not stroke_done and len(pieces) + 1 == stroke_at:
            candidates, values = [("stroke", 0, 0, a0, b0)], [0.0]
        if not candidates:
            break
        side, i, j, a, b = pick(candidates, values)
        if side == "stroke":
            stroke_done = True
            current[1]["S"][0], current[2]["S"][0] = b, a
        else:
            current[1][side][i], current[2][side][j] = b, a
        count[a] += 1
        count[b] += 1
        raced_today.add(frozenset((a, b)))
        pieces.append({"crews": copy_crews(current), "swap": (a, b, side, i, j)})
    if len(pieces) == 1:
        break
    for piece in pieces:
        piece["margin"] = predicted_margin(piece["crews"])
    sessions.append(pieces)

if not sessions:
    st.info("Every useful swap between these athletes has been raced. Pick different athletes or strokes.")
    st.stop()

basis = (f"Using what's been learned from {learned['results_used']} results." if learned
         else "No results yet, so predictions use ergs only. They'll improve as results come in.")
st.write(basis)

# ---- Boat diagram ----------------------------------------------------------
SIDE_FILL = {"S": "#dce8f6", "B": "#f6e7d4"}
SIDE_LINE = {"S": "#2f6aa6", "B": "#a8692b"}
SWAP = "#d1495b"

def seat_layout(boat):
    """Seats from stern (left) to bow (right). Even seats are stroke side."""
    n = len(boat["S"]) + len(boat["B"])
    s_iter, b_iter = iter(boat["S"]), iter(boat["B"])
    return [(k, "S" if k % 2 == 0 else "B", next(s_iter) if k % 2 == 0 else next(b_iter))
            for k in range(n, 0, -1)]

def piece_svg(c, swapped=()):
    n = len(c[1]["S"]) * 2
    seat_w, x0 = 112, 125
    width = x0 + n * seat_w + 80
    centres = {1: 95, 2: 285}
    parts = [f'<svg viewBox="0 0 {width} 380" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;font-family:system-ui,sans-serif">',
             f'<rect x="0" y="0" width="{width}" height="380" rx="14" fill="#f7f8fa"/>']
    seat_xy = {}
    for boat in (1, 2):
        yc = centres[boat]
        sx, bx = x0 - 20, x0 + n * seat_w + 50
        parts.append(f'<text x="18" y="{yc + 5}" font-size="16" font-weight="700" fill="#33404d">Boat {boat}</text>')
        for k, side, name in seat_layout(c[boat]):
            cx = x0 + (n - k) * seat_w + seat_w / 2
            seat_xy[name] = (cx, yc)
            dy = -1 if side == "S" else 1           # stroke side blades on top, bow side below
            parts.append(f'<line x1="{cx}" y1="{yc + dy * 14}" x2="{cx - 30}" y2="{yc + dy * 66}" '
                         f'stroke="#9aa5b1" stroke-width="3" stroke-linecap="round"/>')
            parts.append(f'<rect x="{cx - 44}" y="{yc + dy * 66 - 5}" width="22" height="10" rx="3" '
                         f'fill="{SIDE_LINE[side]}" opacity="0.8"/>')
        parts.append(f'<path d="M{sx},{yc - 24} L{bx - 80},{yc - 24} Q{bx - 15},{yc - 18} {bx},{yc} '
                     f'Q{bx - 15},{yc + 18} {bx - 80},{yc + 24} L{sx},{yc + 24} Q{sx - 14},{yc} {sx},{yc - 24} Z" '
                     f'fill="#ffffff" stroke="#7b8794" stroke-width="2"/>')
        for k, side, name in seat_layout(c[boat]):
            cx, _ = seat_xy[name]
            hot = name in swapped
            parts.append(f'<rect x="{cx - 50}" y="{yc - 17}" width="100" height="34" rx="8" '
                         f'fill="{SIDE_FILL[side]}" stroke="{SWAP if hot else SIDE_LINE[side]}" '
                         f'stroke-width="{3.5 if hot else 1.5}"/>')
            parts.append(f'<text x="{cx}" y="{yc + 5}" font-size="14" text-anchor="middle" '
                         f'font-weight="{700 if hot else 500}" fill="#1f2933">{short_name(name)}</text>')
            seat_label = "Str" if k == n else ("Bow" if k == 1 else str(k))
            parts.append(f'<text x="{cx + 32}" y="{yc - 32}" font-size="11" '
                         f'text-anchor="middle" fill="#616e7c">{seat_label} · {side}</text>')
    if len(swapped) == 2:
        (x1, y1), (x2, y2) = seat_xy[swapped[0]], seat_xy[swapped[1]]
        top, bottom = (x1, y1 + 19), (x2, y2 - 19)
        if y1 > y2:
            top, bottom = (x2, y2 + 19), (x1, y1 - 19)
        parts.append(f'<defs><marker id="h" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" '
                     f'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{SWAP}"/></marker></defs>')
        parts.append(f'<line x1="{top[0]}" y1="{top[1]}" x2="{bottom[0]}" y2="{bottom[1]}" stroke="{SWAP}" '
                     f'stroke-width="3" stroke-dasharray="7 5" marker-start="url(#h)" marker-end="url(#h)"/>')
    parts.append('</svg>')
    return "".join(parts)

# ---- Run sheet -------------------------------------------------------------
def crew_text(boat):
    return ", ".join(short_name(name) for _, _, name in seat_layout(boat))

rows = []
for n_s, pieces in enumerate(sessions, start=1):
    for k, piece in enumerate(pieces, start=1):
        swap = piece["swap"]
        rows.append({
            "Session": n_s,
            "Piece": k,
            "Swap before piece": "Start crews" if swap is None else f"{swap[0]} ↔ {swap[1]}",
            "Boat 1 (stroke → bow)": crew_text(piece["crews"][1]),
            "Boat 2 (stroke → bow)": crew_text(piece["crews"][2]),
            "Predicted margin (Boat 1)": f"{piece['margin']:+.1f} s",
        })
run_sheet = pd.DataFrame(rows)

# ---- Save the plan for recording on the launch -------------------------------
if st.button("Use this plan: save it for recording results", type="primary"):
    plan = {"boat_class": race_in, "piece_length": int(piece_m), "sessions": []}
    for n_s, pieces in enumerate(sessions, start=1):
        plan["sessions"].append({
            "name": f"{date.today()} S{n_s}",
            "pieces": [{
                "boat1": [name for _, _, name in seat_layout(p["crews"][1])],   # stroke to bow
                "boat2": [name for _, _, name in seat_layout(p["crews"][2])],
                "swap": "Start crews" if p["swap"] is None else f"{p['swap'][0]} ↔ {p['swap'][1]}",
            } for p in pieces],
        })
    save_json("saved_plan", plan)
    st.success("Plan saved. Open Enter Piece to record each piece as it's rowed.")

# ---- Show the plan -----------------------------------------------------------
# on a shared screen, hide the rest of the plan so athletes can't see the swaps coming
coach_view = st.toggle("Coach view: show the whole plan", value=True)

def draw(svg):
    """Shows a diagram as an image (newer Streamlit versions strip drawings out of HTML)."""
    data = base64.b64encode(svg.encode()).decode()
    st.markdown(f'<img src="data:image/svg+xml;base64,{data}" style="width:100%" alt="Crews for this piece">',
                unsafe_allow_html=True)

def show_piece(pieces, k):
    piece = pieces[k - 1]
    swap = piece["swap"]
    with st.container(border=True):
        if swap is None:
            st.markdown(f"**Piece {k}: start crews** (baseline). Predicted: Boat 1 {piece['margin']:+.1f} s")
            draw(piece_svg(piece["crews"]))
        else:
            a, b, side, _, _ = swap
            side_word = {"S": "stroke side", "B": "bow side", "stroke": "the strokes swap boats"}[side]
            swing = pieces[k - 2]["margin"] - piece["margin"]
            leader = a if swing >= 0 else b
            st.markdown(f"**Piece {k}: swap {a} ↔ {b}** ({side_word}). Predicted: Boat 1 {piece['margin']:+.1f} s")
            draw(piece_svg(piece["crews"], swapped=(b, a)))
            if coach_view:
                st.caption(f"Model expects {leader} by about {abs(swing) / 2:.1f} s.")

if coach_view:
    st.subheader("Run sheet")
    st.write(f"{piece_m} m pieces, racing in {race_in}. Positive margin = Boat 1 ahead. "
             "Predicted margins are a rough guide.")
    st.download_button("Download full run sheet (CSV)", run_sheet.to_csv(index=False), "seat_race_plan.csv")
    tabs = st.tabs([f"Session {n}" for n in range(1, len(sessions) + 1)])
    for n_s, (tab, pieces) in enumerate(zip(tabs, sessions), start=1):
        with tab:
            st.dataframe(run_sheet[run_sheet["Session"] == n_s].drop(columns="Session"), hide_index=True)
            for k in range(1, len(pieces) + 1):
                show_piece(pieces, k)
else:
    order = [(n_s, k) for n_s, pieces in enumerate(sessions) for k in range(1, len(pieces) + 1)]
    if "plan_step" not in st.session_state:
        st.session_state.plan_step = 0
    step = min(st.session_state.plan_step, len(order) - 1)
    n_s, k = order[step]
    st.subheader(f"Session {n_s + 1}, piece {k}")
    show_piece(sessions[n_s], k)
    b1, b2 = st.columns(2)
    if b1.button("Back", disabled=step == 0):
        st.session_state.plan_step = step - 1
        st.rerun()
    if b2.button("Next piece", disabled=step == len(order) - 1):
        st.session_state.plan_step = step + 1
        st.rerun()

with st.expander("Running it fairly"):
    st.markdown(
        "- Same piece length, rate cap and rest every time; start every piece level.\n"
        "- Coxes and lanes stay with their boat, so lane differences cancel out between pieces.\n"
        "- One timer (or GPS) for every piece, and decide before you start what margin counts.\n"
        "- One result can be noise. Re-race the closest call in a later session.\n"
        "- Leave proper rest between sessions (ideally a few hours) and keep the baseline piece: conditions change.\n"
        "- Treat it as one input alongside ergs and what you see on the water."
    )
