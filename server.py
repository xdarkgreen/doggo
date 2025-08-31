from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.rest import Client
import sqlite3, time, os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

ACC = os.getenv("TWILIO_ACCOUNT_SID")
TOK = os.getenv("TWILIO_AUTH_TOKEN")
FROM = os.getenv("TWILIO_FROM_NUMBER")
PRIMARY = os.getenv("PRIMARY_CONTACT")
tw = Client(ACC, TOK)

DB_PATH = "/data/alerts.db"  # works locally too; Railway volume recommended

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS devices(device_id TEXT PRIMARY KEY, last_seen INTEGER)")
    con.execute("""CREATE TABLE IF NOT EXISTS alerts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER, device_id TEXT, severity TEXT, status TEXT, call_sid TEXT)""")
    return con

@app.get("/")
def root(): return jsonify(ok=True, service="doggolarm-api")

@app.post("/register")
def register():
    j = request.get_json(force=True); d=j.get("device_id","unknown")
    con=db(); con.execute("INSERT OR IGNORE INTO devices VALUES(?,?)",(d,int(time.time())))
    con.commit(); con.close(); return jsonify(ok=True)

@app.post("/health")
def health():
    j = request.get_json(force=True); d=j.get("device_id","unknown")
    con=db(); con.execute("INSERT OR IGNORE INTO devices VALUES(?,0)")
    con.execute("UPDATE devices SET last_seen=? WHERE device_id=?",(int(time.time()),d))
    con.commit(); con.close(); return jsonify(ok=True)

@app.post("/trigger")
def trigger():
    j=request.get_json(force=True); d=j.get("device_id","unknown"); sev=j.get("severity","high")
    spoken=f"Emergency alert from {d}. Severity {sev}. Please check immediately."
    url="https://twimlets.com/message?Message%5B0%5D="+spoken.replace(" ","+")
    call=tw.calls.create(url=url, to=PRIMARY, from_=FROM)
    con=db(); con.execute("INSERT INTO alerts(ts,device_id,severity,status,call_sid) VALUES (?,?,?,?,?)",
                          (int(time.time()), d, sev, "initiated", call.sid))
    con.commit(); con.close(); return jsonify(ok=True, call_sid=call.sid)

@app.get("/devices")
def devices():
    con=db(); rows=con.execute("SELECT device_id,last_seen FROM devices").fetchall(); con.close()
    now=int(time.time())
    return jsonify([{"device_id":d,"last_seen":s,"online":(now-s)<420} for d,s in rows])

@app.get("/alerts")
def alerts():
    limit=int(request.args.get("limit",50))
    con=db(); rows=con.execute("""SELECT ts,device_id,severity,status,call_sid
                                  FROM alerts ORDER BY ts DESC LIMIT ?""",(limit,)).fetchall(); con.close()
    return jsonify([{"ts":r[0],"device_id":r[1],"severity":r[2],"status":r[3],"call_sid":r[4]} for r in rows])
