import requests
import json
import time

OUTPUT_FILE = "test_results.txt"

QUESTIONS = [
    "How many patients do we have?",
    "List all doctors and their specializations",
    "Show me appointments for last month",
    "Which doctor has the most appointments?",
    "What is the total revenue?",
    "Show revenue by doctor",
    "How many cancelled appointments last quarter?",
    "Top 5 patients by spending",
    "Average treatment cost by specialization",
    "Show monthly appointment count for the past 6 months",
    "Which city has the most patients?",
    "List patients who visited more than 3 times",
    "Show unpaid invoices",
    "What percentage of appointments are no-shows?",
    "Show the busiest day of the week for appointments",
    "Revenue trend by month",
    "Average appointment duration by doctor",
    "List patients with overdue invoices",
    "Compare revenue between departments",
    "Show patient registration trend by month"
]

BASE_URL = "http://localhost:8002"

def health_check():
    try:
        res = requests.get(f"{BASE_URL}/health", timeout=5)
        return res.status_code, res.json()
    except Exception as e:
        return "ERROR", str(e)

def ask_question(question):
    try:
        res = requests.post(
            f"{BASE_URL}/chat",
            json={"question": question},
            timeout=10
        )
        return res.status_code, res.json()
    except Exception as e:
        return "ERROR", str(e)

def main():
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

        # Initial Health Check
        f.write("=== INITIAL HEALTH CHECK ===\n")
        status, data = health_check()
        f.write(f"Status: {status}\n")
        f.write(f"Response: {data}\n\n")

        for i, question in enumerate(QUESTIONS, start=1):
            f.write(f"=== Q{i}: {question} ===\n")

            # Health check before each request
            h_status, h_data = health_check()
            f.write(f"[Health] Status: {h_status}\n")

            status, response = ask_question(question)

            if status == "ERROR":
                f.write(f"ERROR: {response}\n\n")
                continue

            f.write(f"HTTP   : {status}\n")
            f.write(f"SQL    : {response.get('sql_query', '—')}\n")
            f.write(f"MSG    : {response.get('message', '—')}\n")
            f.write(f"ROWS   : {response.get('row_count', 0)}\n")
            f.write(f"CACHED : {response.get('cached', False)}\n")

            rows = response.get("rows")
            if rows:
                f.write(f"SAMPLE : {json.dumps(rows[:2], indent=2)}\n")

            f.write("\n")
            time.sleep(0.5)

    print(f"✅ Done. Results saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()