<<<<<<< HEAD
# 🛡️ HealthGuard AI – Smart Student Wellness & Emergency Platform

An AI web app that predicts common student health problems from a daily check-up, explains the result, gives
personalised advice, and sends an **SOS with live location** to guardian, college and hospital when it detects an emergency.

**Stack:** Python · Flask · Scikit-learn · MongoDB · Firebase Cloud · Google Maps API · Twilio SMS · HTML/CSS/JS

## 1. Quick start (5 minutes)

**Step 1 – database (pick one):**
| Option | Command |
|---|---|
| Docker (easiest) | `docker compose up -d` |
| Installed MongoDB | start the `mongod` service |
| MongoDB Atlas (cloud) | put your `mongodb+srv://…` link in `MONGO_URI` in `.env` |

**Step 2 – run the app**
- Windows: double-click **`run.bat`**   ·   Linux/Mac: `./run.sh`
  (creates the virtual environment, installs everything, copies `.env.example` → `.env`, starts the server)
- Open **http://127.0.0.1:5000**

**Step 3 – load demo data (optional but recommended for the presentation)**
```
venv\Scripts\activate        (Linux/Mac: source venv/bin/activate)
python seed_demo.py
```
| Role | Email | Password |
|---|---|---|
| Student (7 days of history) | `demo@student.com` | `demo123` |
| College admin | `admin@college.edu` | `admin123` |

> No MongoDB on the demo laptop? Set `DB_FALLBACK_TO_MOCK=1` in `.env` – the app then starts with a temporary in-memory
> database instead of stopping (data is NOT saved). Check **/technologies** to see which mode you're in.

## 2. What the user experiences
1. **Landing page** → Register (name, roll no, age, **height**, blood group, allergies, guardian phone).
2. After login a new student sees **only an empty health-details form** – no records, no prediction. Every field is required
   and validated (nothing is pre-filled or assumed).
3. **AI result:** predicted condition + probabilities, **wellness score (0-100)**, BMI, **"Why this result"** factors,
   and personalised recommendations. Only now does **My Records** unlock (history table, trend chart, CSV download).
4. **Emergency detection** (fever ≥ 103°F, abnormal heart rate, chest pain, breathing difficulty, fainting, feeling unsafe)
   → 10-second cancellable countdown → **SOS SMS + live location** to guardian, college authority and hospital.
5. **Admin dashboard** (register with `ADMIN_EMAIL`): campus statistics, condition chart, students needing attention, SOS log.
6. **/technologies**: live health-check of every technology with test buttons for Firebase and SMS.

## 3. Architecture
```
Browser (HTML/CSS/JS, Google Maps)  ──►  Flask (app.py)  ──►  Scikit-learn RandomForest (model/health_model.pkl)
                                            │  ├──►  MongoDB   users · records · alerts   (permanent storage)
                                            │  ├──►  Firebase Firestore   (optional cloud backup, no passwords)
                                            │  └──►  Twilio SMS   (SOS alerts)
```
| File | Purpose |
|---|---|
| `app.py` | routes, validation, auth, DB, emergency logic, integrations |
| `train_model.py` | builds the dataset, trains + evaluates the model (5-fold CV), saves metrics |
| `seed_demo.py` | demo users and a week of realistic check-ups |
| `templates/`, `static/` | pages, styling, check-up/SOS/map JavaScript (charts are offline – no CDN needed) |

## 4. Setting up each integration (all optional – the app works without them)
| Technology | How to enable | Without it |
|---|---|---|
| Firebase Cloud | Firebase console → Project settings → Service accounts → *Generate new private key*; enable **Firestore**; set `FIREBASE_CREDENTIALS=serviceAccount.json` | no cloud backup |
| Google Maps | Google Cloud → enable *Maps JavaScript API* + *Places API* → `GOOGLE_MAPS_API_KEY` | link to Google Maps still works |
| Twilio SMS | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` (trial accounts text verified numbers only) | SMS printed in terminal (simulation) |

Phone numbers must be international format (`+919876543210`).

## 5. Suggested 3-minute demo
1. Landing page → **/technologies** (show all 8 technologies working).
2. Register a new student → show the **empty form** (no auto-prediction).
3. Submit normal values → *Healthy*, score ~100. Submit fever 100.6 + cough/sore throat/body ache → *Flu* with "Why this result".
4. Submit temperature **103.5** (or tick *Chest pain*) → **emergency countdown → SOS** (SMS text in terminal or real SMS).
5. Log in as demo student → **My Records** trend chart · log in as admin → dashboard.

## 6. Honest notes (say these in the viva – judges respect it)
- **The training data is synthetic**: generated from medically-inspired rules, because no public student dataset is bundled.
  The ~96% accuracy therefore measures how well the model learned those rules, **not** real-world clinical accuracy.
  To improve: replace `make_dataset()` in `train_model.py` with a real labelled CSV and retrain.
- Output is a **screening aid, not a diagnosis**; emergency thresholds are simple, transparent rules on purpose (safety-critical).
- The wellness score is a heuristic: 30% model's "Healthy" probability + 70% share of vitals/lifestyle values in normal range.
- Not yet included (future work): CSRF tokens, rate limiting, HTTPS/production server (use gunicorn + reverse proxy), real-time wearables.

## Troubleshooting
| Problem | Fix |
|---|---|
| `Could not connect to MongoDB` | start MongoDB / `docker compose up -d` / fix `MONGO_URI`; or `DB_FALLBACK_TO_MOCK=1` for a quick demo |
| Map is blank | add `GOOGLE_MAPS_API_KEY` |
| SMS only in terminal | add Twilio keys (simulation mode is expected without them) |
| Location unavailable | allow location in the browser (works on `localhost`; other hosts need HTTPS) |
=======
# mini-project
my project - Healthguard AI
>>>>>>> 2ef22698224ab6e1cc6dcd9bbc25daca7615c57b
