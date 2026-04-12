
import sqlite3
import random
from datetime import datetime, date, timedelta
import os

DB_PATH = "clinic.db"

# ── Seed data ──────────────────────────────────────────────────────────────────

FIRST_NAMES_M = [
    "Arun", "Rahul", "Vikram", "Suresh", "Manoj", "Arjun", "Karthik",
    "Sanjay", "Rajesh", "Deepak", "Nikhil", "Amit", "Rohan", "Vishal",
    "Ganesh", "Pradeep", "Naveen", "Ajay", "Ravi", "Mohan", "Harish",
    "Senthil", "Bala", "Dinesh", "Vignesh", "Praveen", "Sachin",
    "Anand", "Vivek", "Ramesh",
]
FIRST_NAMES_F = [
    "Priya", "Divya", "Kavya", "Meena", "Lakshmi", "Ananya", "Nithya",
    "Swetha", "Revathi", "Geetha", "Aishwarya", "Pooja", "Sneha",
    "Lavanya", "Kalpana", "Saranya", "Deepa", "Anitha", "Pavithra",
    "Janani", "Uma", "Shalini", "Bhavana", "Mythili", "Hema",
    "Padma", "Rani", "Shobha", "Vijaya", "Sunita",
]
LAST_NAMES = [
    "Kumar", "Sharma", "Gupta", "Patel", "Singh", "Reddy", "Nair",
    "Iyer", "Menon", "Pillai", "Rao", "Joshi", "Shah", "Mehta",
    "Naidu", "Verma", "Mishra", "Pandey", "Chopra", "Bose",
    "Das", "Ghosh", "Sen", "Mukherjee", "Chatterjee",
]
CITIES = [
    "Chennai", "Bangalore", "Mumbai", "Delhi", "Hyderabad",
    "Coimbatore", "Madurai", "Pune", "Kolkata", "Ahmedabad",
]
SPECIALIZATIONS = [
    "Dermatology", "Cardiology", "Orthopedics", "General", "Pediatrics"
]
DEPARTMENTS = {
    "Dermatology": "Skin & Hair",
    "Cardiology": "Heart & Vascular",
    "Orthopedics": "Bone & Joint",
    "General": "General Medicine",
    "Pediatrics": "Child Health",
}
DOCTOR_NAMES = [
    "Dr. Arjun Mehta", "Dr. Priya Nair", "Dr. Suresh Reddy", "Dr. Kavitha Iyer",
    "Dr. Ramesh Kumar", "Dr. Ananya Sharma", "Dr. Vikram Patel", "Dr. Lakshmi Rao",
    "Dr. Ganesh Pillai", "Dr. Sneha Menon", "Dr. Deepak Singh", "Dr. Revathi Nair",
    "Dr. Arun Joshi", "Dr. Meena Gupta", "Dr. Bala Krishnan",
]
TREATMENT_NAMES = {
    "Dermatology": ["Chemical Peel", "Laser Hair Removal", "Acne Treatment",
                    "Skin Biopsy", "Phototherapy"],
    "Cardiology": ["ECG", "Echocardiogram", "Stress Test", "Holter Monitor",
                   "Angioplasty"],
    "Orthopedics": ["X-Ray", "Physiotherapy Session", "Joint Injection",
                    "Bone Density Test", "Cast Application"],
    "General": ["Blood Test", "Urine Analysis", "General Checkup",
                "Vaccination", "Nebulization"],
    "Pediatrics": ["Growth Assessment", "Vaccination", "Developmental Screening",
                   "Allergy Test", "Nutritional Counseling"],
}
STATUSES = ["Scheduled", "Completed", "Cancelled", "No-Show"]
STATUS_WEIGHTS = [0.15, 0.60, 0.15, 0.10]
INVOICE_STATUSES = ["Paid", "Pending", "Overdue"]
INVOICE_WEIGHTS = [0.55, 0.25, 0.20]


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def random_datetime(start: date, end: date) -> datetime:
    d = random_date(start, end)
    hour = random.randint(8, 17)
    minute = random.choice([0, 15, 30, 45])
    return datetime(d.year, d.month, d.day, hour, minute)


def maybe_null(value, probability=0.15):
    """Return None with given probability, else return the value."""
    return None if random.random() < probability else value


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ── Schema ──────────────────────────────────────────────────────────────
    cur.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE patients (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name      TEXT NOT NULL,
        last_name       TEXT NOT NULL,
        email           TEXT,
        phone           TEXT,
        date_of_birth   DATE,
        gender          TEXT,
        city            TEXT,
        registered_date DATE
    );

    CREATE TABLE doctors (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        specialization  TEXT,
        department      TEXT,
        phone           TEXT
    );

    CREATE TABLE appointments (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id       INTEGER REFERENCES patients(id),
        doctor_id        INTEGER REFERENCES doctors(id),
        appointment_date DATETIME,
        status           TEXT,
        notes            TEXT
    );

    CREATE TABLE treatments (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        appointment_id   INTEGER REFERENCES appointments(id),
        treatment_name   TEXT,
        cost             REAL,
        duration_minutes INTEGER
    );

    CREATE TABLE invoices (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id   INTEGER REFERENCES patients(id),
        invoice_date DATE,
        total_amount REAL,
        paid_amount  REAL,
        status       TEXT
    );
    """)

    today = date.today()
    year_ago = today - timedelta(days=365)

    # ── Doctors ─────────────────────────────────────────────────────────────
    doctor_rows = []
    specs_cycle = (SPECIALIZATIONS * 4)[:15]  # 3 doctors per spec
    for i, name in enumerate(DOCTOR_NAMES):
        spec = specs_cycle[i]
        dept = DEPARTMENTS[spec]
        phone = maybe_null(f"+91-{random.randint(70000,99999)}{random.randint(10000,99999)}")
        doctor_rows.append((name, spec, dept, phone))
    cur.executemany(
        "INSERT INTO doctors (name, specialization, department, phone) VALUES (?,?,?,?)",
        doctor_rows,
    )
    doctor_ids = [r[0] for r in cur.execute("SELECT id FROM doctors").fetchall()]
    doctor_specs = {
        r[0]: r[1]
        for r in cur.execute("SELECT id, specialization FROM doctors").fetchall()
    }

    # ── Patients ─────────────────────────────────────────────────────────────
    patient_rows = []
    for _ in range(200):
        gender = random.choice(["M", "F"])
        fname = random.choice(FIRST_NAMES_M if gender == "M" else FIRST_NAMES_F)
        lname = random.choice(LAST_NAMES)
        email = maybe_null(f"{fname.lower()}.{lname.lower()}{random.randint(1,99)}@email.com")
        phone = maybe_null(f"+91-{random.randint(70000,99999)}{random.randint(10000,99999)}")
        dob = random_date(date(1950, 1, 1), date(2010, 12, 31))
        city = random.choice(CITIES)
        reg_date = random_date(year_ago, today)
        patient_rows.append((fname, lname, email, phone, dob, gender, city, reg_date))
    cur.executemany(
        """INSERT INTO patients
           (first_name, last_name, email, phone, date_of_birth, gender, city, registered_date)
           VALUES (?,?,?,?,?,?,?,?)""",
        patient_rows,
    )
    patient_ids = [r[0] for r in cur.execute("SELECT id FROM patients").fetchall()]

    # Build visit-weight so some patients visit a lot
    visit_weights = []
    for pid in patient_ids:
        w = random.choices([1, 2, 3, 4, 5, 6], weights=[30, 25, 20, 12, 8, 5])[0]
        visit_weights.append(w)
    total_weight = sum(visit_weights)
    visit_probs = [w / total_weight for w in visit_weights]

    # Build doctor-load weights
    doctor_weights = [random.choices([1, 2, 3, 4, 5], weights=[5, 10, 25, 35, 25])[0]
                      for _ in doctor_ids]
    doc_total = sum(doctor_weights)
    doc_probs = [w / doc_total for w in doctor_weights]

    # ── Appointments ─────────────────────────────────────────────────────────
    appt_rows = []
    for _ in range(500):
        pid = random.choices(patient_ids, weights=visit_probs)[0]
        did = random.choices(doctor_ids, weights=doc_probs)[0]
        appt_dt = random_datetime(year_ago, today)
        status = random.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
        notes = maybe_null(
            random.choice([
                "Follow-up required", "Patient doing well",
                "Referred to specialist", "Medication adjusted",
                "Routine checkup", "Lab results pending",
            ]),
            probability=0.30,
        )
        appt_rows.append((pid, did, appt_dt, status, notes))
    cur.executemany(
        "INSERT INTO appointments (patient_id, doctor_id, appointment_date, status, notes) VALUES (?,?,?,?,?)",
        appt_rows,
    )

    # ── Treatments (linked to Completed appointments) ─────────────────────────
    completed = cur.execute(
        "SELECT id, doctor_id FROM appointments WHERE status='Completed'"
    ).fetchall()
    random.shuffle(completed)
    treatment_appts = completed[:350]
    treatment_rows = []
    for appt_id, doc_id in treatment_appts:
        spec = doctor_specs.get(doc_id, "General")
        tname = random.choice(TREATMENT_NAMES.get(spec, TREATMENT_NAMES["General"]))
        cost = round(random.uniform(50, 5000), 2)
        duration = random.choice([15, 20, 30, 45, 60, 90, 120])
        treatment_rows.append((appt_id, tname, cost, duration))
    cur.executemany(
        "INSERT INTO treatments (appointment_id, treatment_name, cost, duration_minutes) VALUES (?,?,?,?)",
        treatment_rows,
    )

    # ── Invoices ─────────────────────────────────────────────────────────────
    invoice_patient_sample = random.choices(patient_ids, k=300)
    invoice_rows = []
    for pid in invoice_patient_sample:
        inv_date = random_date(year_ago, today)
        total = round(random.uniform(200, 8000), 2)
        status = random.choices(INVOICE_STATUSES, weights=INVOICE_WEIGHTS)[0]
        if status == "Paid":
            paid = total
        elif status == "Pending":
            paid = round(random.uniform(0, total * 0.5), 2)
        else:  # Overdue
            paid = round(random.uniform(0, total * 0.3), 2)
        invoice_rows.append((pid, inv_date, total, paid, status))
    cur.executemany(
        "INSERT INTO invoices (patient_id, invoice_date, total_amount, paid_amount, status) VALUES (?,?,?,?,?)",
        invoice_rows,
    )

    conn.commit()

    # ── Summary ──────────────────────────────────────────────────────────────
    counts = {
        tbl: cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        for tbl in ["patients", "doctors", "appointments", "treatments", "invoices"]
    }
    conn.close()

    print(
        f"✅  Database created: {DB_PATH}\n"
        f"   Created {counts['patients']} patients, {counts['doctors']} doctors, "
        f"{counts['appointments']} appointments, {counts['treatments']} treatments, "
        f"{counts['invoices']} invoices."
    )


if __name__ == "__main__":
    main()
