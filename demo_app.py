# Starting file for the public demo. It runs exactly the same app as app.py.
# Streamlit won't deploy the same file twice, so the demo starts here instead.
# What keeps the demo on the made-up squad is its secrets: demo = true
exec(open("app.py", encoding="utf-8").read())
