"""Fills the database with a demo student, an admin and a week of check-ups so the site looks alive in a demo.

Run ONCE (with real MongoDB running):   python seed_demo.py
Logins created:
    student : demo@student.com   /  demo123
    admin   : admin@college.edu  /  admin123   (matches ADMIN_EMAIL in .env)
"""
import os, uuid, datetime as dt
from werkzeug.security import generate_password_hash
import app as A

if A.DB_MODE == "mock":
    raise SystemExit("Seeding an in-memory database is pointless (it disappears when this script ends). "
                     "Start MongoDB and set USE_MOCK_DB=0 first.")


def make_user(name, email, pw, roll, height, gender="Female", blood="O+", phone="+919876543210"):
    if A.users.find_one({"email": email}):
        print("exists:", email); return A.users.find_one({"email": email})
    u = dict(_id=uuid.uuid4().hex, name=name, email=email, roll_no=roll, age="20", height=float(height), gender=gender,
             blood_group=blood, allergies="none", guardian_name="Guardian", guardian_phone=phone,
             password=generate_password_hash(pw), created=A.now())
    A.users.insert_one(u); A.cloud_backup("users", u); print("created:", email); return u


def checkup(t, hr, water, sleep, weight, stress, **sym):
    d = dict(temperature=t, heart_rate=hr, water_intake=water, sleep_hours=sleep, weight=weight, stress_level=stress)
    d.update({k: int(sym.get(k, 0)) for k in A.SYMPTOMS})
    return d


demo = make_user("Demo Student", "demo@student.com", "demo123", "CS2026-01", 168)
admin_email = os.getenv("ADMIN_EMAIL", "admin@college.edu").lower()
make_user("College Admin", admin_email, "admin123", "STAFF-01", 172, gender="Other")
others = [make_user("Rahul Verma", "rahul@student.com", "demo123", "CS2026-02", 175, "Male", "B+"),
          make_user("Priya Singh", "priya@student.com", "demo123", "CS2026-03", 160, "Female", "A+")]

if A.records.count_documents({"user_id": demo["_id"]}) == 0:
    today = dt.datetime.now()
    story = [  # a week in the life: stress -> dehydration -> flu -> recovery
        checkup(98.4, 72, 2.6, 7.5, 58, 2),
        checkup(98.5, 80, 2.2, 5.0, 58, 6, headache=1),
        checkup(98.4, 86, 2.0, 4.5, 58, 9, headache=1, fatigue=1),
        checkup(98.8, 98, 0.8, 6.5, 57, 4, headache=1, dizziness=1, fatigue=1),
        checkup(100.6, 88, 1.8, 6.0, 57, 4, cough=1, sore_throat=1, body_ache=1, fatigue=1, headache=1),
        checkup(99.6, 82, 2.4, 8.0, 57, 3, cough=1, fatigue=1),
        checkup(98.4, 73, 2.8, 7.5, 58, 2),
    ]
    for i, d in enumerate(story):
        when = (today - dt.timedelta(days=len(story) - 1 - i)).strftime("%Y-%m-%d %H:%M:%S")
        A.analyse(demo, d, created=when)
    print(f"added {len(story)} check-ups for the demo student")

for u, d in [(others[0], checkup(103.6, 120, 1.2, 5.0, 70, 5, headache=1, body_ache=1, chest_pain=0)),
             (others[1], checkup(98.6, 96, 1.0, 5.5, 52, 5, pale_skin=1, fatigue=1, dizziness=1))]:
    if A.records.count_documents({"user_id": u["_id"]}) == 0:
        A.analyse(u, d)
print("Done. Open http://127.0.0.1:5000  and log in with demo@student.com / demo123")
