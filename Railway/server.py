from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
import sqlite3, time, os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

ACC = os.getenv("TWILIO_ACCOUNT_SID")
TOK = os.getenv("TWILIO_AUTH_TOKEN")
FROM = os.getenv("TWILIO_FROM_NUMBER")  # e.g. +12694158101
PRIMARY = os.getenv("PRIMARY_CONTACT")  # e.g. +14844676513
tw = Client(ACC, TOK)

def db():
    con = sqlite3.connect("alerts.db")
    con.execute("""CREATE TABLE IF NOT EXISTS devices(
        device_id TEXT PRIMARY KEY, last_seen INTEGER
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS alerts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER, device_id TEXT, severity TEXT, status TEXT, call_sid TEXT
    )""")
    return con

@app.post("/register")
def register():
    j = request.get_json(force=True)
    device_id = j.get("device_id","unknown")
    con = db()
    con.execute("INSERT OR IGNORE INTO devices(device_id,last_seen) VALUES (?,?)",
                (device_id, int(time.time())))
    con.commit(); con.close()
    return jsonify(ok=True)

@app.post("/health")
def health():
    j = request.get_json(force=True)
    device_id = j.get("device_id","unknown")
    con = db()
    con.execute("INSERT OR IGNORE INTO devices(device_id,last_seen) VALUES (?,?)",
                (device_id, 0))
    con.execute("UPDATE devices SET last_seen=? WHERE device_id=?",
                (int(time.time()), device_id))
    con.commit(); con.close()
    return jsonify(ok=True)

@app.post("/trigger")
def trigger():
    j = request.get_json(force=True)
    device_id = j.get("device_id","unknown")
    severity  = j.get("severity","high")
    spoken = f"Emergency alert from {device_id}. Severity {severity}. Please check immediately."
    url = "https://twimlets.com/message?Message%5B0%5D=" + spoken.replace(" ","+")
    call = tw.calls.create(url=url, to=PRIMARY, from_=FROM)

    con = db()
    con.execute("INSERT INTO alerts(ts,device_id,severity,status,call_sid) VALUES (?,?,?,?,?)",
                (int(time.time()), device_id, severity, "initiated", call.sid))
    con.commit(); con.close()
    return jsonify(ok=True, call_sid=call.sid)

@app.post("/test-call")
def test_call():
    to = request.get_json(force=True).get("to", PRIMARY)
    call = tw.calls.create(url="https://twimlets.com/message?Message%5B0%5D=This+is+a+test+call",
                           to=to, from_=FROM)
    return jsonify(ok=True, call_sid=call.sid)

@app.get("/devices")
def devices():
    con = db()
    rows = con.execute("SELECT device_id,last_seen FROM devices").fetchall()
    con.close()
    now = int(time.time())
    out = [{"device_id": d, "last_seen": s, "online": (now - s) < 7*60} for d,s in rows]
    return jsonify(out)

@app.get("/alerts")
def alerts():
    limit = int(request.args.get("limit", 50))
    con = db()
    rows = con.execute("""SELECT ts,device_id,severity,status,call_sid
                          FROM alerts ORDER BY ts DESC LIMIT ?""",(limit,)).fetchall()
    con.close()
    out = [{"ts": r[0], "device_id": r[1], "severity": r[2], "status": r[3], "call_sid": r[4]}
           for r in rows]
    return jsonify(out)

# health check for Railway
@app.get("/")
def root():
    return jsonify(ok=True, service="doggolarm-api")
