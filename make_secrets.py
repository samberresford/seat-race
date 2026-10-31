"""
Sets your admin password, and prints the text for Streamlit Cloud's Secrets box.
Squads and their passwords are made inside the app, on the Access page.

Nothing is uploaded anywhere. Run:  python make_secrets.py
"""
import json
import tomllib

with open(".streamlit/secrets.toml", "rb") as f:
    sheet_url = tomllib.load(f)["sheet_url"]
with open("gsheets_key.json") as f:
    key = json.load(f)

print("Your admin password lets you see every squad and make passwords for new ones.")
admin = input("Admin password: ").strip()
settings = [f"sheet_url = {json.dumps(sheet_url)}", f"admin_password = {json.dumps(admin)}"]

with open(".streamlit/secrets.toml", "w") as f:
    f.write("\n".join(settings) + "\n")
print("\nSaved to .streamlit/secrets.toml on this Mac.")

print("\n----- copy everything below this line into Streamlit Cloud -> Secrets -----\n")
print("\n".join(settings))
print("\n[gcp_service_account]")
for name, value in key.items():
    print(f"{name} = {json.dumps(value)}")
print("\n----- copy everything above this line -----")
