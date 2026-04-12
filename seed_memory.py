from vanna_setup import agent_memory

SEED_PAIRS = [
    # ── Patient queries ───────────────────────────────────────────────────────
    (
        "How many patients do we have?",
        "SELECT COUNT(*) AS total_patients FROM patients",
    ),
    (
        "List all patients in Chennai",
        "SELECT first_name, last_name, email, phone FROM patients WHERE city = 'Chennai'",
    ),
    (
        "How many female patients are there?",
        "SELECT COUNT(*) AS female_patients FROM patients WHERE gender = 'F'",
    ),
    (
        "Which city has the most patients?",
        """SELECT city, COUNT(*) AS patient_count
           FROM patients
           GROUP BY city
           ORDER BY patient_count DESC
           LIMIT 1""",
    ),
    (
        "List patients who registered in the last 30 days",
        """SELECT first_name, last_name, registered_date
           FROM patients
           WHERE registered_date >= DATE('now', '-30 days')
           ORDER BY registered_date DESC""",
    ),

    # ── Doctor queries ────────────────────────────────────────────────────────
    (
        "List all doctors and their specializations",
        "SELECT name, specialization, department FROM doctors ORDER BY specialization",
    ),
    (
        "Which doctor has the most appointments?",
        """SELECT d.name, COUNT(a.id) AS appointment_count
           FROM doctors d
           JOIN appointments a ON a.doctor_id = d.id
           GROUP BY d.id, d.name
           ORDER BY appointment_count DESC
           LIMIT 1""",
    ),
    (
        "Show appointments per doctor",
        """SELECT d.name, d.specialization, COUNT(a.id) AS total_appointments
           FROM doctors d
           LEFT JOIN appointments a ON a.doctor_id = d.id
           GROUP BY d.id, d.name
           ORDER BY total_appointments DESC""",
    ),

    # ── Appointment queries ───────────────────────────────────────────────────
    (
        "How many cancelled appointments are there?",
        """SELECT COUNT(*) AS cancelled_count
           FROM appointments
           WHERE status = 'Cancelled'""",
    ),
    (
        "Show monthly appointment count for the past 6 months",
        """SELECT strftime('%Y-%m', appointment_date) AS month,
                  COUNT(*) AS appointment_count
           FROM appointments
           WHERE appointment_date >= DATE('now', '-6 months')
           GROUP BY month
           ORDER BY month""",
    ),
    (
        "List patients who visited more than 3 times",
        """SELECT p.first_name, p.last_name, COUNT(a.id) AS visit_count
           FROM patients p
           JOIN appointments a ON a.patient_id = p.id
           GROUP BY p.id
           HAVING visit_count > 3
           ORDER BY visit_count DESC""",
    ),

    # ── Financial queries ─────────────────────────────────────────────────────
    (
        "What is the total revenue?",
        "SELECT SUM(total_amount) AS total_revenue FROM invoices WHERE status = 'Paid'",
    ),
    (
        "Show revenue by doctor",
        """SELECT d.name, SUM(i.total_amount) AS total_revenue
           FROM invoices i
           JOIN appointments a ON a.patient_id = i.patient_id
           JOIN doctors d ON d.id = a.doctor_id
           GROUP BY d.id, d.name
           ORDER BY total_revenue DESC""",
    ),
    (
        "Show unpaid invoices",
        """SELECT p.first_name, p.last_name, i.total_amount, i.paid_amount,
                  (i.total_amount - i.paid_amount) AS balance, i.status
           FROM invoices i
           JOIN patients p ON p.id = i.patient_id
           WHERE i.status IN ('Pending', 'Overdue')
           ORDER BY i.status, balance DESC""",
    ),

    # ── Time-based queries ────────────────────────────────────────────────────
    (
        "Show patient registration trend by month",
        """SELECT strftime('%Y-%m', registered_date) AS month,
                  COUNT(*) AS new_patients
           FROM patients
           GROUP BY month
           ORDER BY month""",
    ),
    (
        "Average treatment cost by specialization",
        """SELECT d.specialization, ROUND(AVG(t.cost), 2) AS avg_cost
           FROM treatments t
           JOIN appointments a ON a.id = t.appointment_id
           JOIN doctors d ON d.id = a.doctor_id
           GROUP BY d.specialization
           ORDER BY avg_cost DESC""",
    ),
]


def seed():
    print(f"Seeding {len(SEED_PAIRS)} Q&A pairs into agent memory…")
    for question, sql in SEED_PAIRS:
        agent_memory.save_question_sql(question=question, sql=sql)
        print(f"  ✓  {question}")
    print(f"\n✅  Done — {len(SEED_PAIRS)} pairs seeded.")


if __name__ == "__main__":
    seed()
