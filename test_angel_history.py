import os

import pyotp
from dotenv import load_dotenv
from SmartApi import SmartConnect

load_dotenv(os.path.join("backend", ".env"))

api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
totp = pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
session = api.generateSession(
    os.environ["ANGEL_CLIENT_ID"], os.environ["ANGEL_PASSWORD"], totp
)
print("login:", session.get("status"), session.get("message"))
if not session.get("status"):
    raise SystemExit("login failed; check the .env values")

resp = api.getCandleData({
    "exchange": "NSE",
    "symboltoken": "2885",          # RELIANCE
    "interval": "FIVE_MINUTE",
    "fromdate": "2026-10-15 09:15",
    "todate": "2026-10-15 15:30",
})
print("candles:", resp.get("status"), resp.get("message"), resp.get("errorcode"))
rows = resp.get("data") or []
print("bars:", len(rows))
for r in rows[:3] + rows[-3:]:
    print(r)
print("has 11:45 IST bar:", any(r[0][11:16] == "11:45" for r in rows))
