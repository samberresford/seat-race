"""
Where the app keeps its data, and who can see it.

With a Google Sheet set up (online, or on your Mac with gsheets_key.json), everything is saved
to the sheet. Each squad gets its own tabs and its own password, and only ever sees its own data.
Nobody using the app sees the sheet itself: only you and the app's service account can open it.
Without a sheet, the app falls back to CSV and JSON files in this folder.
In the public demo (demo = true in its secrets), every visitor gets their own copy of the
made-up squad and pretend season, kept only in their browser tab, so nobody can change it for anyone else.
"""
import hmac
import json
import os

import pandas as pd
import streamlit as st

PIECE_COLUMNS = ["session", "piece", "boat_class", "piece_length", "boat1", "boat2",
                 "margin", "lane1", "conditions"]
SQUAD_COLUMNS = ["name", "side", "best_2k", "coach_rank"]


# ---- Settings and the sheet ---------------------------------------------------------
def _setting(name):
    """A value from .streamlit/secrets.toml (or Streamlit Cloud's secrets), if there is one."""
    try:
        return st.secrets[name]
    except Exception:
        return None


@st.cache_resource
def _sheet():
    """The Google Sheet, or None if it isn't set up (then we use local files)."""
    url = _setting("sheet_url")
    if not url:
        return None
    import gspread
    if os.path.exists("gsheets_key.json"):                       # on your Mac
        client = gspread.service_account(filename="gsheets_key.json")
    elif _setting("gcp_service_account"):                         # online
        client = gspread.service_account_from_dict(dict(_setting("gcp_service_account")))
    else:
        return None
    return client.open_by_url(url)


def demo():
    return bool(_setting("demo"))


def where():
    if demo():
        return "this browser tab only (it's a demo: changes vanish when you close it)"
    return "Google Sheet" if _sheet() is not None else "files on this computer"


def _demo_data(name, start):
    """The demo keeps each visitor's data in their own session, starting from the made-up files."""
    if name not in st.session_state:
        st.session_state[name] = start()
    return st.session_state[name]


def _squads():
    """Squad name -> password. Empty means a single squad."""
    found = _setting("squads")
    return dict(found) if found else {}


def current_squad():
    return st.session_state.get("squad")


# ---- Reading and writing tabs --------------------------------------------------------
def _write_tab(tab, table):
    tab.clear()
    rows = [list(table.columns)] + table.astype(object).where(table.notna(), "").values.tolist()
    tab.update(rows, value_input_option="RAW")        # RAW stops Sheets turning 6:31.8 into a time


def _tab(base, columns, local_file, squad):
    """A squad's tab (e.g. 'Senior Men | pieces'), created empty the first time it's needed.
    Shared tabs (like the list of accounts) have no squad in their name."""
    book = _sheet()
    title = f"{squad} | {base}" if squad else base
    try:
        return book.worksheet(title)
    except Exception:
        pass
    start = pd.DataFrame(columns=columns)
    if not squad and local_file and os.path.exists(local_file):
        start = pd.read_csv(local_file)                  # single-squad mode: bring in local files
    tab = book.add_worksheet(title=title, rows=1000, cols=max(len(start.columns), 2))
    _write_tab(tab, start)
    return tab


@st.cache_data(ttl=15)
def _read_tab(base, columns, local_file, squad):
    records = _tab(base, columns, local_file, squad).get_all_records(numericise_ignore=["all"])
    table = pd.DataFrame(records) if records else pd.DataFrame(columns=columns)
    return table.replace("", None)


def _read(base, columns, local_file=None):
    return _read_tab(base, columns, local_file, current_squad())


def _write(base, columns, table):
    _write_tab(_tab(base, columns, None, current_squad()), table)
    _read_tab.clear()


# ---- The squad and the pieces ----------------------------------------------------------
def _local_squad_file():
    return "squad.csv" if os.path.exists("squad.csv") else "sample_squad.csv"


def load_squad():
    if demo():
        table = _demo_data("demo_squad", lambda: pd.read_csv("sample_squad.csv")).copy()
    elif _sheet() is not None:
        table = _read("squad", SQUAD_COLUMNS, _local_squad_file())
    else:
        table = pd.read_csv(_local_squad_file())
    for column in SQUAD_COLUMNS:
        if column not in table:
            table[column] = None
    table["coach_rank"] = pd.to_numeric(table["coach_rank"], errors="coerce")
    return table.dropna(subset=["name"])


def save_squad(table):
    if demo():
        st.session_state["demo_squad"] = table.copy()
    elif _sheet() is not None:
        _write("squad", SQUAD_COLUMNS, table)
    else:
        table.to_csv(_local_squad_file(), index=False)


def load_pieces():
    if demo():
        start = lambda: pd.read_csv("sim_pieces.csv") if os.path.exists("sim_pieces.csv") else pd.DataFrame(columns=PIECE_COLUMNS)
        table = _demo_data("demo_pieces", start).copy()
    elif _sheet() is not None:
        table = _read("pieces", PIECE_COLUMNS, "pieces.csv")
    elif os.path.exists("pieces.csv"):
        table = pd.read_csv("pieces.csv")
    else:
        table = pd.DataFrame(columns=PIECE_COLUMNS)
    for column in PIECE_COLUMNS:
        if column not in table:
            table[column] = None
    for column in ["piece", "piece_length", "margin"]:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table.dropna(subset=["session"])


def save_pieces(table):
    """Saves the whole pieces table, so anything removed here is removed from the sheet too."""
    if demo():
        st.session_state["demo_pieces"] = table.copy()
    elif _sheet() is not None:
        _write("pieces", PIECE_COLUMNS, table)
    else:
        table.to_csv("pieces.csv", index=False)


# ---- Small settings: the saved plan, pairs to race next --------------------------------
def load_json(name):
    if demo():
        return _demo_data("demo_settings", dict).get(name)
    if _sheet() is not None:
        settings = _read("settings", ["key", "value"])
        found = settings[settings["key"] == name]["value"] if not settings.empty else []
        return json.loads(found.iloc[0]) if len(found) else None
    if os.path.exists(f"{name}.json"):
        with open(f"{name}.json") as f:
            return json.load(f)
    return None


def save_json(name, value):
    if demo():
        _demo_data("demo_settings", dict)[name] = value
    elif _sheet() is not None:
        settings = _read("settings", ["key", "value"])
        settings = settings[settings["key"] != name] if not settings.empty else pd.DataFrame(columns=["key", "value"])
        settings = pd.concat([settings, pd.DataFrame([{"key": name, "value": json.dumps(value)}])])
        _write("settings", ["key", "value"], settings)
    else:
        with open(f"{name}.json", "w") as f:
            json.dump(value, f, indent=1)


# ---- Accounts: one password per squad, at your club or another club --------------------
ACCOUNT_COLUMNS = ["name", "salt", "hash", "created"]
WORDS = ["catch", "drive", "finish", "feather", "square", "slide", "rigger", "gate", "blade", "spoon",
         "stroke", "bow", "cox", "eight", "pair", "quad", "scull", "sweep", "river", "regatta", "head",
         "launch", "bank", "lock", "weir", "buoy", "wash", "ratio", "rhythm", "power", "swing", "crew"]


def _hash(password, salt):
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def load_accounts():
    if _sheet() is None:
        return pd.DataFrame(columns=ACCOUNT_COLUMNS)
    return _read_tab("access", ACCOUNT_COLUMNS, None, None)


def add_account(name):
    """Makes a squad account and returns its new password. Only a scrambled version is stored,
    so the password can't be read back later: note it down when it's shown."""
    import secrets
    from datetime import date
    password = "-".join(secrets.choice(WORDS) for _ in range(3)) + "-" + str(secrets.randbelow(90) + 10)
    salt = secrets.token_hex(16)
    accounts = load_accounts()
    accounts = accounts[accounts["name"] != name] if not accounts.empty else accounts
    row = pd.DataFrame([{"name": name, "salt": salt, "hash": _hash(password, salt), "created": str(date.today())}])
    _write_tab(_tab("access", ACCOUNT_COLUMNS, None, None), pd.concat([accounts, row], ignore_index=True))
    _read_tab.clear()
    return password


def remove_account(name):
    """Stops a password working. The squad's data stays in the sheet."""
    accounts = load_accounts()
    _write_tab(_tab("access", ACCOUNT_COLUMNS, None, None), accounts[accounts["name"] != name])
    _read_tab.clear()


def copy_old_data_into(squad):
    """Copies the squad and pieces saved before squads existed into one squad's tabs."""
    for base, columns in [("squad", SQUAD_COLUMNS), ("pieces", PIECE_COLUMNS)]:
        try:
            old = _sheet().worksheet(base).get_all_records(numericise_ignore=["all"])
        except Exception:
            old = []
        if old:
            _write_tab(_tab(base, columns, None, squad), pd.DataFrame(old))
    _read_tab.clear()


def all_squads():
    names = list(_squads())
    accounts = load_accounts()
    if not accounts.empty:
        names += [n for n in accounts["name"] if n not in names]
    return names


def is_admin():
    return bool(st.session_state.get("admin"))


# ---- Signing in ------------------------------------------------------------------------
def require_password():
    """Each squad signs in with its own password and only ever sees its own squad.
    The admin password (yours) can switch between squads. With no passwords set
    (the public demo, or local files on your Mac) the app is open."""
    squads, admin, single = _squads(), _setting("admin_password"), _setting("password")
    if not (squads or admin or single):
        st.session_state.admin = True                    # open app (demo, or your Mac without passwords)
        if demo():
            st.sidebar.info("Demo with a made-up squad and a pretend season. Try anything: "
                            "your changes only last until you close the tab.")
        return

    if not st.session_state.get("signed_in"):
        st.title("Seat Racing")
        entered = st.text_input("Squad password", type="password")
        if entered:
            same = lambda pw: pw is not None and hmac.compare_digest(entered, str(pw))
            match = next((name for name, pw in squads.items() if same(pw)), None)
            if not match:
                for r in load_accounts().itertuples():
                    if hmac.compare_digest(_hash(entered, r.salt), r.hash):
                        match = r.name
                        break
            if same(admin):
                st.session_state.update(signed_in=True, admin=True, squad=next(iter(all_squads()), None))
                st.rerun()
            elif match or same(single):
                st.session_state.update(signed_in=True, admin=False, squad=match)
                st.rerun()
            st.error("That password isn't right.")
        st.stop()

    with st.sidebar:
        names = all_squads()
        if st.session_state.get("admin") and names:
            chosen = st.selectbox("Squad", names, index=names.index(st.session_state.squad)
                                  if st.session_state.get("squad") in names else 0)
            st.session_state.squad = chosen
        elif st.session_state.get("squad"):
            st.write(f"Squad: **{st.session_state.squad}**")
        if st.button("Sign out"):
            for key in ["signed_in", "admin", "squad"]:
                st.session_state.pop(key, None)
            st.rerun()
