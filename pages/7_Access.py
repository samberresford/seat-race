import pandas as pd
import streamlit as st
from storage import (add_account, copy_old_data_into, is_admin, load_accounts, remove_account,
                     require_password, where)

require_password()
st.title("Access")

if not is_admin():
    st.info("Only the admin can manage squads and passwords.")
    st.stop()
if where() != "Google Sheet":
    st.info("Squad accounts need the Google Sheet. Without it, the app runs as one open squad.")
    st.stop()

st.caption("Every squad, at your club or another club, gets its own password and only ever sees "
           "its own athletes and results. Nobody but you can open the Google Sheet itself.")

# ---- Squads with access ----------------------------------------------------------------
accounts = load_accounts()
st.subheader("Squads with access")
if accounts.empty:
    st.write("None yet.")
else:
    st.dataframe(accounts[["name", "created"]], hide_index=True)

# ---- Add a squad ---------------------------------------------------------------------------
st.subheader("Add a squad, or give one a new password")
name = st.text_input("Squad name", placeholder="e.g. UOEBC Senior Men, or Bath UBC Women")
if st.button("Create password", type="primary", disabled=not name.strip()):
    st.session_state.new_password = (name.strip(), add_account(name.strip()))

if st.session_state.get("new_password"):
    squad, password = st.session_state.new_password
    st.success(f"Password for {squad}:")
    st.code(password, language=None)
    st.warning("Copy it now and send it to that squad's captain. It's stored scrambled, so it can't be "
               "shown again. If it's lost, create a new one: the old password stops working.")
    if st.button("Done, I've copied it"):
        st.session_state.pop("new_password")
        st.rerun()

# ---- Remove a squad's access -----------------------------------------------------------------
if not accounts.empty:
    with st.expander("Remove a squad's access"):
        target = st.selectbox("Squad", list(accounts["name"]), key="remove_squad")
        sure = st.checkbox(f"Yes, stop {target}'s password working. Their data stays in the sheet.",
                           key="remove_sure")
        if st.button("Remove access", disabled=not sure):
            remove_account(target)
            st.rerun()

    with st.expander("Move data saved before squads existed into a squad"):
        st.write("Copies the squad list and pieces from the original tabs into one squad's tabs. "
                 "Use it once, for your own squad.")
        target = st.selectbox("Squad", list(accounts["name"]), key="copy_squad")
        sure = st.checkbox(f"Yes, copy the original data into {target} (replaces what's there)", key="copy_sure")
        if st.button("Copy data", disabled=not sure):
            copy_old_data_into(target)
            st.success(f"Copied into {target}.")
