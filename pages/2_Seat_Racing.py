import pandas as pd
import streamlit as st
from model import BOATS, BOAT_SPEED, load_squad, short_name, tech_slider

st.title("Seat Racing Plan")
st.caption("Picks who races, builds two even crews, then plans one swap per piece.")

tech_impact = tech_slider()
squad = load_squad(tech_impact)
power = dict(zip(squad["name"], squad["boat_watts"]))   # name -> tech-adjusted watts
gap = dict(zip(squad["name"], squad["gap"]))            # name -> your order vs model

# ---- Settings --------------------------------------------------------------
c1, c2, c3, c4 = st.columns(4)
select_for = c1.selectbox("Selecting for", list(BOATS.keys()))
race_in = c2.selectbox("Racing in", list(BOATS.keys()), index=1)
piece_m = c3.number_input("Piece (m)", 500, 2000, 1000, 250)
n_pieces = c4.number_input("Pieces", 2, 8, 5)

per_side_cut = BOATS[select_for] // 2     # seats per side in the boat you're selecting
need = BOATS[race_in]                      # athletes per side: two boats x half a crew

# ---- Who's racing ----------------------------------------------------------
# default: the athletes ranked closest to the selection cut on each side
def default_racers(side):
    side_df = squad[squad["side"] == side].copy()
    # blend the model's rank with yours, so people either of you sees as borderline get picked
    blended = (side_df["side_rank"] + side_df.get("coach_rank", side_df["side_rank"])) / 2
    side_df["distance"] = (blended - (per_side_cut + 0.5)).abs()
    return side_df.sort_values(["distance", "side_rank"])["name"].head(need).tolist()

racers = {}
with st.expander(f"Who's racing ({need} per side)", expanded=True):
    col_s, col_b = st.columns(2)
    for col, side, label in [(col_s, "S", "Stroke side"), (col_b, "B", "Bow side")]:
        options = squad[squad["side"] == side].sort_values("side_rank")["name"].tolist()
        racers[side] = col.multiselect(label, options, default=default_racers(side))

for side, label in [("S", "stroke side"), ("B", "bow side")]:
    if len(racers[side]) != need:
        st.warning(f"Pick exactly {need} on {label} (you have {len(racers[side])}). "
                   f"Racing in {race_in} needs {need // 2} per side in each boat.")
        st.stop()

# ---- Balanced base crews ---------------------------------------------------
# deal athletes out like picking teams: 1st to Boat 1, 2nd and 3rd to Boat 2, 4th to Boat 1...
# bow side starts the other way round so the two strongest don't end up together
crews = {1: {"S": [], "B": []}, 2: {"S": [], "B": []}}
for side, pattern in [("S", [1, 2, 2, 1]), ("B", [2, 1, 1, 2])]:
    ordered = sorted(racers[side], key=lambda n: power[n], reverse=True)
    for i, name in enumerate(ordered):
        crews[pattern[i % 4]][side].append(name)

def boat_power(boat):
    return sum(power[n] for side in "SB" for n in boat[side])

# then try every same-side swap and keep any that makes the boats closer
improved = True
while improved:
    improved = False
    for side in "SB":
        for i, a in enumerate(crews[1][side]):
            for j, b in enumerate(crews[2][side]):
                before = abs(boat_power(crews[1]) - boat_power(crews[2]))
                crews[1][side][i], crews[2][side][j] = b, a
                if abs(boat_power(crews[1]) - boat_power(crews[2])) < before - 0.1:
                    improved = True
                    a = b  # keep the swap
                else:
                    crews[1][side][i], crews[2][side][j] = a, b  # undo

piece_seconds = piece_m / BOAT_SPEED[race_in]

def predicted_margin(c):
    """Boat 1's predicted lead in seconds: speed goes with the cube root of power."""
    p1, p2 = boat_power(c[1]), boat_power(c[2])
    return piece_seconds * (p1 - p2) / (3 * (p1 + p2) / 2)

# ---- Swap plan -------------------------------------------------------------
# each piece swaps one same-side pair. Best pairs: close in power, ones where your
# order and the model disagree, and people who haven't been swapped much yet.
def copy_crews(c):
    return {b: {s: list(c[b][s]) for s in "SB"} for b in (1, 2)}

pieces = [{"crews": copy_crews(crews), "swap": None}]
swap_count = {n: 0 for side in "SB" for n in racers[side]}
raced = set()
current = copy_crews(crews)

for p in range(1, int(n_pieces)):
    best = None
    for side in "SB":
        for i, a in enumerate(current[1][side]):
            for j, b in enumerate(current[2][side]):
                if frozenset((a, b)) in raced:
                    continue
                score = abs(power[a] - power[b]) - 5 * (abs(gap[a]) + abs(gap[b])) \
                        + 20 * (swap_count[a] + swap_count[b])
                if best is None or score < best[0]:
                    best = (score, side, i, j, a, b)
    if best is None:
        break
    _, side, i, j, a, b = best
    current[1][side][i], current[2][side][j] = b, a
    swap_count[a] += 1
    swap_count[b] += 1
    raced.add(frozenset((a, b)))
    pieces.append({"crews": copy_crews(current), "swap": (a, b, side, i, j)})

for piece in pieces:
    piece["margin"] = predicted_margin(piece["crews"])

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
for k, piece in enumerate(pieces, start=1):
    swap = piece["swap"]
    rows.append({
        "Piece": k,
        "Swap before piece": "Start crews" if swap is None else f"{swap[0]} ↔ {swap[1]}",
        "Boat 1 (stroke → bow)": crew_text(piece["crews"][1]),
        "Boat 2 (stroke → bow)": crew_text(piece["crews"][2]),
        "Predicted margin (Boat 1)": f"{piece['margin']:+.1f} s",
    })
run_sheet = pd.DataFrame(rows)
if len(pieces) < n_pieces:
    st.info(f"Only {len(pieces)} pieces: every useful swap between these athletes is already in the plan.")

st.subheader("Run sheet")
st.write(f"{len(pieces)} × {piece_m} m, racing in {race_in}. Positive margin = Boat 1 ahead. "
         "Predictions use the tech-adjusted ranking, so treat them as a rough guide.")
st.dataframe(run_sheet, hide_index=True)
st.download_button("Download run sheet (CSV)", run_sheet.to_csv(index=False), "seat_race_plan.csv")

# ---- Piece by piece --------------------------------------------------------
st.subheader("Piece by piece")
for k, piece in enumerate(pieces, start=1):
    with st.container(border=True):
        swap = piece["swap"]
        if swap is None:
            st.markdown(f"**Piece {k}: start crews.** Predicted: Boat 1 {piece['margin']:+.1f} s")
            st.html(piece_svg(piece["crews"]))
        else:
            a, b, side, _, _ = swap
            side_word = "stroke side" if side == "S" else "bow side"
            swing = pieces[k - 2]["margin"] - piece["margin"]
            leader, trailer = (a, b) if swing >= 0 else (b, a)
            st.markdown(f"**Piece {k}: swap {a} ↔ {b}** ({side_word}). "
                        f"Predicted: Boat 1 {piece['margin']:+.1f} s")
            st.html(piece_svg(piece["crews"], swapped=(b, a)))
            st.caption(f"Compares {a} with {b}. In the calculator: Athlete A = {a}, Athlete B = {b}, "
                       f"Piece 1 margin = Boat 1's margin in piece {k - 1}, Piece 2 margin = piece {k}. "
                       f"Model expects {leader} by about {abs(swing) / 2:.1f} s.")

with st.expander("Running it fairly"):
    st.markdown(
        "- Same piece length, rate cap and rest every time; start every piece level.\n"
        "- Coxes and lanes stay with their boat, so lane differences cancel out between pieces.\n"
        "- One timer (or GPS) for every piece, and decide before you start what margin counts.\n"
        "- One result can be noise. Swap the closest pair back at the end, or repeat on another day.\n"
        "- Treat it as one input alongside ergs and what you see on the water."
    )
