"""HealthGuard AI - Smart Student Wellness & Emergency Platform (Flask backend)."""
import os, re, sys, json, uuid, datetime as dt
from functools import wraps
import joblib
import pandas as pd
from dotenv import load_dotenv
from flask import (Flask, render_template, request, redirect, url_for, session, jsonify, flash)
from werkzeug.security import generate_password_hash, check_password_hash
from train_model import FEATURES, MODEL_PATH, METRICS_PATH, main as train_main

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

# ---------------------------------------------------------------- MongoDB
DB_MODE = "mongo"          # "mongo" (real, persistent) or "mock" (in-memory, demo only)


def connect_db():
    """Connect to MongoDB (local or Atlas) and verify the connection at startup.

    USE_MOCK_DB=1 -> in-memory database for quick demos only (data is lost on restart).
    USE_MOCK_DB=0 -> real MongoDB using MONGO_URI / DB_NAME from .env  (default).
    """
    global DB_MODE
    db_name = os.getenv("DB_NAME", "healthguard")
    if os.getenv("USE_MOCK_DB", "0") == "1":
        import mongomock
        DB_MODE = "mock"
        print("[DB] Using IN-MEMORY mock database - data will be lost on restart.")
        return mongomock.MongoClient()[db_name]
    from pymongo import MongoClient
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")           # fail fast if MongoDB is not reachable
    except Exception as e:
        if os.getenv("DB_FALLBACK_TO_MOCK", "0") == "1":      # optional safety net for live demos
            import mongomock
            DB_MODE = "mock"
            print(f"[DB] WARNING: MongoDB unreachable ({e}). Falling back to IN-MEMORY database - data will NOT be saved.")
            return mongomock.MongoClient()[db_name]
        raise SystemExit(
            f"\n[DB] Could not connect to MongoDB at {uri}\n     Reason: {e}\n"
            "     -> Start MongoDB (or run: docker compose up -d), or fix MONGO_URI in .env.\n"
            "     -> For a quick demo without MongoDB set USE_MOCK_DB=1.\n")
    print(f"[DB] Connected to MongoDB database '{db_name}'.")
    return client[db_name]


db = connect_db()
users, records, alerts = db.users, db.records, db.alerts
users.create_index("email", unique=True)                      # one account per email
records.create_index([("user_id", 1), ("created", -1)])       # fast per-student history
alerts.create_index([("created", -1)])

# ---------------------------------------------------------------- ML model
def load_model():
    """Load the trained model; (re)train automatically if missing or saved with another scikit-learn version."""
    if os.path.exists(MODEL_PATH):
        try:
            return joblib.load(MODEL_PATH)
        except Exception as e:
            print("[ML] Saved model could not be loaded (%s) - retraining." % e)
    train_main()
    return joblib.load(MODEL_PATH)


model = load_model()


def now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- Firebase (cloud backup to Firestore)
_fs = None
FIREBASE = {"last_ok": None, "last_error": None}     # live status shown on the Technologies page


def firebase_configured():
    cred = os.getenv("FIREBASE_CREDENTIALS", "")
    return bool(cred) and os.path.exists(cred)


def _firestore():
    global _fs
    if _fs is None:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS")))
        _fs = firestore.client()
    return _fs


def cloud_backup(collection, doc):
    """Copy a document to Firebase Firestore (password never leaves MongoDB). Never breaks the app."""
    if not firebase_configured():
        return "not_configured"
    try:
        safe = {k: v for k, v in doc.items() if k != "password"}
        _firestore().collection(collection).document(str(doc["_id"])).set(safe)
        FIREBASE.update(last_ok=now(), last_error=None)
        return "ok"
    except Exception as e:
        FIREBASE["last_error"] = str(e)[:200]
        print("[Firebase] backup failed:", e)
        return "failed"


# ---------------------------------------------------------------- Twilio SMS
TWILIO = {"last_ok": None, "last_error": None}


def twilio_configured():
    return all(os.getenv(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"))


def valid_phone(p):
    """E.164 format, e.g. +919876543210 (Twilio rejects anything else)."""
    return bool(re.fullmatch(r"\+[1-9]\d{7,14}", (p or "").strip()))


def send_sms(to, body):
    to = (to or "").strip()
    if not valid_phone(to):
        return "skipped: invalid number (use +countrycode..., e.g. +919876543210)"
    if not twilio_configured():
        print(f"[SMS SIMULATED] -> {to}: {body}")
        return "simulated"
    try:
        from twilio.rest import Client
        Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN")).messages.create(
            to=to, from_=os.getenv("TWILIO_FROM_NUMBER"), body=body)
        TWILIO.update(last_ok=now(), last_error=None)
        return "sent"
    except Exception as e:
        TWILIO["last_error"] = str(e)[:200]
        return f"failed: {e}"


# ---------------------------------------------------------------- Helpers
def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if "uid" not in session:
            return (jsonify(error="login required"), 401) if request.path.startswith("/api") else redirect(url_for("login"))
        return f(*a, **k)
    return wrap


def has_records(uid):
    """True once the student has completed at least one health check-up."""
    return records.count_documents({"user_id": uid}) > 0


@app.context_processor
def inject_first_time():
    # Used by base.html: hide "My Records" until the first check-up is done.
    uid = session.get("uid")
    return {"first_time": bool(uid) and not has_records(uid)}


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def flag(v):
    return 1 if str(v) in ("1", "true", "True", "on") else 0


RECS = {
    "Healthy": ["Great! Keep your current routine.", "Do 30 minutes of physical activity most days.",
                "Eat fruits, vegetables and protein with every main meal."],
    "Fever": ["Rest and drink plenty of fluids (water, ORS, soup).", "Monitor temperature every 4-6 hours.",
              "Light, easily digestible food (khichdi, fruit, curd).", "Visit the campus clinic if fever lasts more than 2 days."],
    "Flu": ["Rest, stay hydrated, and avoid close contact with roommates.", "Warm fluids, steam inhalation and honey-ginger tea can ease symptoms.",
            "Wear a mask in class/hostel common areas.", "Consult a doctor if symptoms worsen or last more than 3 days."],
    "Dehydration": ["Sip water or ORS steadily - do not gulp.", "Add coconut water, lemon water, buttermilk.",
                    "Avoid excess tea, coffee and energy drinks today.", "Seek medical help if dizziness or confusion continues."],
    "Anemia": ["Eat iron-rich foods: spinach, beetroot, dates, jaggery, lentils, eggs.", "Pair iron foods with vitamin C (lemon, amla, orange).",
               "Avoid tea/coffee right after meals.", "Get a hemoglobin (CBC) blood test at the campus clinic."],
    "Stress": ["Try 4-7-8 breathing or 10 minutes of meditation.", "Take short breaks (5 min every hour) while studying.",
               "Do light exercise or a walk; talk to a friend or counselor.", "Keep a fixed sleep schedule - avoid screens 30 min before bed."],
}


def bmi_category(b):
    if b is None: return None
    return "Underweight" if b < 18.5 else "Normal" if b < 25 else "Overweight" if b < 30 else "Obese"


def key_factors(d, bmi):
    """Transparent 'why this result' list: which of the student's inputs are outside normal ranges."""
    f = []
    t, hr = d["temperature"], d["heart_rate"]
    if t >= 99.5: f.append(f"Temperature {t}°F is above normal (about 97-99°F)")
    elif t < 97: f.append(f"Temperature {t}°F is below normal")
    if hr > 100: f.append(f"Heart rate {int(hr)} bpm is above the normal resting range (60-100)")
    elif hr < 50: f.append(f"Heart rate {int(hr)} bpm is below the normal resting range")
    if d["water_intake"] < 1.5: f.append(f"Water intake {d['water_intake']} L is low (aim for 2-3 L)")
    if d["sleep_hours"] < 6: f.append(f"Sleep {d['sleep_hours']} h is short (aim for 7-8 h)")
    if d["stress_level"] >= 7: f.append(f"Stress level {int(d['stress_level'])}/10 is high")
    names = {"cough": "cough", "headache": "headache", "sore_throat": "sore throat", "body_ache": "body ache",
             "fatigue": "fatigue", "dizziness": "dizziness", "pale_skin": "pale skin / weakness"}
    sym = [n for k, n in names.items() if d[k]]
    if sym: f.append("Reported symptoms: " + ", ".join(sym))
    if bmi and bmi_category(bmi) != "Normal": f.append(f"BMI {bmi} is in the '{bmi_category(bmi)}' range")
    return f or ["All values are within normal ranges and no symptoms were reported"]


def recommendations(label, d, bmi=None):
    weight = d.get("weight")
    water = round(weight * 0.033, 1) if weight else 2.5
    out = list(RECS[label])
    out.append(f"Water target: about {max(water, 2.0)} L/day (you logged {d['water_intake']} L).")
    if d["sleep_hours"] < 7:
        out.append(f"Sleep: you logged {d['sleep_hours']} h - aim for 7-8 h with a consistent bedtime.")
    if bmi and bmi_category(bmi) in ("Underweight", "Overweight", "Obese"):
        out.append(f"BMI {bmi} ({bmi_category(bmi)}): a balanced diet and regular exercise can help; a campus dietitian/doctor can give a plan.")
    if d["stress_level"] >= 7:
        out.append("Stress is high: campus counselor / Tele-MANAS helpline 14416 (free, 24x7) can help.")
    return out


def detect_emergency(d):
    r = []
    if d["temperature"] >= 103: r.append("Very high fever (103°F or above)")
    if d["heart_rate"] >= 130 or d["heart_rate"] <= 45: r.append(f"Abnormal heart rate ({int(d['heart_rate'])} bpm)")
    if d["chest_pain"]: r.append("Chest pain")
    if d["breathing_difficulty"]: r.append("Difficulty breathing")
    if d["fainting"]: r.append("Fainting / loss of consciousness")
    if d["unsafe"]: r.append("Student reports feeling unsafe / thoughts of self-harm")
    return r


# ---------------------------------------------------------------- Auth (Step 1: User Registration)
@app.route("/")
def home():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        email = f.get("email", "").strip().lower()
        if not email or len(f.get("password", "")) < 6:
            flash("Enter a valid email and a password of at least 6 characters.")
        elif num(f.get("height")) is None or not 100 <= num(f.get("height")) <= 230:
            flash("Enter your height in cm (100-230) - it is used to calculate BMI.")
        elif not valid_phone(f.get("guardian_phone", "")):
            flash("Guardian phone must include the country code, e.g. +919876543210 (needed for SOS SMS).")
        elif users.find_one({"email": email}):
            flash("Email already registered.")
        else:
            u = dict(_id=uuid.uuid4().hex, name=f["name"].strip(), email=email, roll_no=f.get("roll_no", ""),
                     age=f.get("age", ""), height=num(f.get("height")), gender=f.get("gender", ""), blood_group=f.get("blood_group", ""),
                     allergies=f.get("allergies", ""), guardian_name=f.get("guardian_name", ""),
                     guardian_phone=f.get("guardian_phone", "").strip(),
                     password=generate_password_hash(f["password"]), created=now())
            try:
                users.insert_one(u)
            except Exception:
                if users.find_one({"email": email}):      # unique-index race / duplicate
                    flash("Email already registered.")
                    return render_template("register.html")
                raise
            cloud_backup("users", u)
            flash("Registered successfully. Please log in and fill in your health details.")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = users.find_one({"email": request.form.get("email", "").strip().lower()})
        if u and check_password_hash(u["password"], request.form.get("password", "")):
            session.update(uid=u["_id"], name=u["name"].split()[0],
                           admin=(u["email"] == os.getenv("ADMIN_EMAIL", "").lower()))
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- Steps 2-5: data -> AI -> recommendations -> emergency detection
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", maps_key=os.getenv("GOOGLE_MAPS_API_KEY", ""),
                           first_time=not has_records(session["uid"]))


# Every value below is REQUIRED - nothing is assumed or auto-filled.
REQUIRED_NUMERIC = {          # field: (label, min, max)
    "temperature":  ("Body temperature (°F)", 94, 108),
    "heart_rate":   ("Heart rate (bpm)", 30, 220),
    "water_intake": ("Water intake (L)", 0, 10),
    "sleep_hours":  ("Sleep (hours)", 0, 24),
    "weight":       ("Weight (kg)", 20, 250),
    "stress_level": ("Stress level (1-10)", 1, 10),
}
SYMPTOMS = ("cough", "headache", "sore_throat", "body_ache", "fatigue", "dizziness", "pale_skin",
            "chest_pain", "breathing_difficulty", "fainting", "unsafe")


def validate_checkup(j):
    """Return (clean_data, errors). Missing / out-of-range values are errors, never defaulted."""
    d, errors = {}, {}
    for k, (label, lo, hi) in REQUIRED_NUMERIC.items():
        v = num(j.get(k))
        if v is None:
            errors[k] = f"{label} is required."
        elif not lo <= v <= hi:
            errors[k] = f"{label} must be between {lo} and {hi}."
        else:
            d[k] = v
    d.update({k: flag(j.get(k)) for k in SYMPTOMS})
    return d, errors


def wellness_score(d, bmi, healthy_p):
    """0-100 score: 30% model's 'Healthy' probability + 70% how many vitals/lifestyle values are in the normal range."""
    checks = [97 <= d["temperature"] < 99.5, 50 <= d["heart_rate"] <= 100, d["water_intake"] >= 1.5,
              d["sleep_hours"] >= 6, d["stress_level"] < 7, bmi is None or 18.5 <= bmi < 25]
    n_symptoms = sum(d[k] for k in ("cough", "headache", "sore_throat", "body_ache", "fatigue", "dizziness", "pale_skin"))
    vitals = max(0.0, sum(checks) / len(checks) - min(0.2, 0.04 * n_symptoms))
    return round(100 * (0.3 * healthy_p + 0.7 * vitals))


def analyse(user, d, created=None):
    """Steps 3-5: ML prediction + wellness score + recommendations + emergency detection. Saves the record."""
    h = num(user.get("height"))
    bmi = round(d["weight"] / ((h / 100) ** 2), 1) if h else None
    x = pd.DataFrame([[d[k] for k in FEATURES]], columns=FEATURES)
    probs = sorted(zip(model.classes_, model.predict_proba(x)[0]), key=lambda t: -t[1])
    label, conf = probs[0][0], float(probs[0][1])
    healthy_p = next((float(p) for l, p in probs if l == "Healthy"), 0.0)
    reasons = detect_emergency(d)
    score = wellness_score(d, bmi, healthy_p)
    if reasons:
        score = min(score, 30)                       # an emergency can never look like a "healthy" score
    rec = dict(_id=uuid.uuid4().hex, user_id=user["_id"], created=created or now(), prediction=label,
               confidence=round(conf * 100, 1), emergency=bool(reasons), wellness_score=score, bmi=bmi, **d)
    records.insert_one(rec)
    cloud_backup("records", rec)
    return dict(prediction=label, confidence=round(conf * 100, 1), wellness_score=score, bmi=bmi,
                bmi_category=bmi_category(bmi), low_confidence=conf < 0.5,
                probabilities=[{"label": l, "pct": round(float(p) * 100, 1)} for l, p in probs[:4]],
                factors=key_factors(d, bmi), recommendations=recommendations(label, d, bmi),
                emergency=bool(reasons), reasons=reasons)


@app.post("/api/assess")
@login_required
def assess():
    j = request.get_json(silent=True) or {}
    d, errors = validate_checkup(j)
    if errors:
        return jsonify(error="Please fill in all required health details.", fields=errors), 400
    return jsonify(analyse(users.find_one({"_id": session["uid"]}), d))


# ---------------------------------------------------------------- Step 6: Emergency alert (Twilio + live location)
@app.post("/api/sos")
@login_required
def sos():
    j = request.get_json(force=True)
    lat, lng, reason = j.get("lat"), j.get("lng"), j.get("reason", "Manual SOS")
    u = users.find_one({"_id": session["uid"]})
    last = next(iter(records.find({"user_id": u["_id"]}).sort("created", -1).limit(1)), None)
    health = (f"Last check-up: {last['prediction']}, temp {last['temperature']}F, HR {last.get('heart_rate') or 'NA'}"
              if last else "No health data yet")
    loc = f"https://maps.google.com/?q={lat},{lng}" if lat is not None and lng is not None else "location unavailable"
    msg = (f"HEALTHGUARD SOS: {u['name']} (Roll {u['roll_no']}, Blood {u['blood_group']}, "
           f"Allergies: {u['allergies'] or 'none'}) needs help. Reason: {reason}. {health}. Location: {loc}")
    targets = [("guardian", u["guardian_phone"]), ("college_authority", os.getenv("COLLEGE_AUTHORITY_PHONE")),
               ("nearby_hospital", os.getenv("HOSPITAL_PHONE"))]
    results = {name: send_sms(ph, msg) for name, ph in targets if ph and "XXXX" not in ph}
    a = dict(_id=uuid.uuid4().hex, user_id=u["_id"], student=u["name"], roll_no=u["roll_no"], created=now(),
             reason=reason, lat=lat, lng=lng, message=msg, delivery=results)
    alerts.insert_one(a)
    cloud_backup("alerts", a)
    return jsonify(ok=True, delivery=results or {"note": "No phone numbers configured"}, message=msg)


# ---------------------------------------------------------------- Health record management
@app.route("/records")
@login_required
def records_page():
    if not has_records(session["uid"]):
        flash("Please complete your first health check-up before viewing records.")
        return redirect(url_for("dashboard"))
    return render_template("records.html")


@app.get("/api/records")
@login_required
def api_records():
    rows = list(records.find({"user_id": session["uid"]}).sort("created", 1))
    keep = ("created", "prediction", "confidence", "wellness_score", "bmi", "temperature", "heart_rate", "sleep_hours",
            "water_intake", "stress_level", "emergency")
    return jsonify([{k: r.get(k) for k in keep} for r in rows])


@app.get("/records/export")
@login_required
def export_records():
    import csv, io
    from flask import Response
    cols = ["created", "prediction", "confidence", "wellness_score", "bmi", "temperature", "heart_rate", "water_intake",
            "sleep_hours", "weight", "stress_level", "emergency"]
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(cols)
    for r in records.find({"user_id": session["uid"]}).sort("created", 1):
        w.writerow([r.get(c, "") for c in cols])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=my_health_records.csv"})


# ---------------------------------------------------------------- College / admin view
@app.route("/admin")
@login_required
def admin():
    if not session.get("admin"):
        flash("Admin access only.")
        return redirect(url_for("dashboard"))
    counts, latest, n_checkups, n_emerg = {}, {}, 0, 0
    for r in records.find({}).sort("created", 1):
        counts[r["prediction"]] = counts.get(r["prediction"], 0) + 1
        latest[r["user_id"]] = r                      # ends up as each student's most recent check-up
        n_checkups += 1
        n_emerg += 1 if r.get("emergency") else 0
    names = {u["_id"]: u for u in users.find({})}
    attention = [dict(name=names[uid]["name"], roll=names[uid].get("roll_no", ""), prediction=r["prediction"],
                      score=r.get("wellness_score"), emergency=r.get("emergency"), when=r["created"])
                 for uid, r in latest.items() if uid in names and (r.get("emergency") or r["prediction"] != "Healthy")]
    attention.sort(key=lambda a: (not a["emergency"], a["score"] if a["score"] is not None else 100))
    all_alerts = list(alerts.find({}).sort("created", -1).limit(50))
    return render_template("admin.html", alerts=all_alerts, counts=counts, attention=attention,
                           stats=dict(students=users.count_documents({}), checkups=n_checkups,
                                      emergencies=n_emerg, alerts=alerts.count_documents({})))


# ---------------------------------------------------------------- Technologies used (live status of every integration)
def _ver(pkg):
    try:
        from importlib.metadata import version
        return version(pkg)
    except Exception:
        return "not installed"


def mongo_status():
    if DB_MODE == "mock":
        return dict(state="warn", detail="In-memory demo database - data is lost on restart. Set USE_MOCK_DB=0.")
    try:
        db.client.admin.command("ping")
        return dict(state="ok", detail=f"Connected to database '{db.name}' - {users.count_documents({})} users, "
                                       f"{records.count_documents({})} records saved permanently.")
    except Exception as e:
        return dict(state="error", detail=f"Connection lost: {str(e)[:120]}")


def tech_status():
    try:
        m = json.load(open(METRICS_PATH))
    except Exception:
        m = {}
    fb = ("ok" if FIREBASE["last_ok"] else "warn") if firebase_configured() else "off"
    tw = ("ok" if twilio_configured() else "off")
    fb_detail = {"off": "Not configured - add FIREBASE_CREDENTIALS in .env to back up data to Firestore.",
                 "warn": "Configured. Waiting for the first backup - use the test button.",
                 "ok": f"Working. Last backup: {FIREBASE['last_ok']}"}[fb]
    if FIREBASE["last_error"]:
        fb, fb_detail = "error", "Last backup failed: " + FIREBASE["last_error"]
    tw_detail = ("Twilio keys found - real SMS will be sent." if tw == "ok" else
                 "Simulation mode - SMS text is printed in the terminal. Add Twilio keys in .env to send real SMS.")
    if TWILIO["last_error"]:
        tw, tw_detail = "error", "Last SMS failed: " + TWILIO["last_error"]
    maps_ok = bool(os.getenv("GOOGLE_MAPS_API_KEY"))
    return [
        dict(key="python", cat="Programming Language", name="Python", icon="🐍", state="ok", detail=f"Running Python {sys.version.split()[0]}."),
        dict(key="sklearn", cat="Machine Learning", name="Scikit-learn", icon="🧠", state="ok" if m else "warn",
             detail=(f"RandomForest (scikit-learn {_ver('scikit-learn')}) - {m.get('accuracy', 0) * 100:.1f}% test accuracy, "
                     f"{m.get('cv_accuracy', 0) * 100:.1f}% 5-fold CV, {m.get('samples', 0)} synthetic samples, "
                     f"{len(m.get('classes', []))} conditions.") if m else "Model loaded."),
        dict(key="frontend", cat="Frontend", name="HTML, CSS, JavaScript", icon="🖥️", state="ok", detail="Templates and static files are being served."),
        dict(key="flask", cat="Backend Framework", name="Flask", icon="🧱", state="ok", detail=f"Flask {_ver('flask')} is serving this page."),
        dict(key="mongo", cat="Database", name="MongoDB", icon="🗄️", **mongo_status()),
        dict(key="firebase", cat="Cloud Storage", name="Firebase Cloud", icon="☁️", state=fb, detail=fb_detail, test="/api/test/firebase"),
        dict(key="maps", cat="Maps", name="Google Maps API", icon="📍", state="ok" if maps_ok else "off",
             detail="API key found - live map and nearby hospitals are enabled on the Check-up page." if maps_ok else
                    "No key - add GOOGLE_MAPS_API_KEY in .env (Maps JavaScript API + Places API). A Google Maps hospital link still works."),
        dict(key="twilio", cat="Emergency Alerts", name="Twilio SMS API", icon="💬", state=tw, detail=tw_detail, test="/api/test/sms"),
    ]


@app.route("/technologies")
def technologies():
    return render_template("technologies.html", techs=tech_status())


@app.get("/api/status")
def api_status():
    return jsonify([{k: t[k] for k in ("key", "name", "state", "detail")} for t in tech_status()])


@app.post("/api/test/firebase")
@login_required
def test_firebase():
    if not firebase_configured():
        return jsonify(ok=False, message="Firebase is not configured. Set FIREBASE_CREDENTIALS in .env."), 400
    r = cloud_backup("healthcheck", dict(_id="ping-" + session["uid"], user_id=session["uid"], tested=now()))
    return jsonify(ok=r == "ok", message="Test document written to Firestore collection 'healthcheck'." if r == "ok"
                   else "Firebase write failed: " + str(FIREBASE["last_error"]))


@app.post("/api/test/sms")
@login_required
def test_sms():
    u = users.find_one({"_id": session["uid"]})
    to = u.get("guardian_phone", "")
    r = send_sms(to, f"HealthGuard AI test message for {u['name']}. SMS alerts are working.")
    return jsonify(ok=r in ("sent", "simulated"), message=f"Guardian number {to}: {r}" +
                   (" (add Twilio keys in .env to send for real)" if r == "simulated" else ""))


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "1") == "1", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")))
