"""Run this to populate sample attendance data: python seed.py"""
import requests, random
from datetime import datetime, timedelta

URL = "http://127.0.0.1:5000/api/attendance"

employees = [
    ("EMP001", "Akhilesh Lonkar",  "Engineering"),
    ("EMP002", "Priya Sharma",     "HR"),
    ("EMP003", "Rohan Mehta",      "Finance"),
    ("EMP004", "Anjali Singh",     "Marketing"),
    ("EMP005", "Vikram Patil",     "Engineering"),
    ("EMP006", "Sneha Kulkarni",   "Operations"),
    ("EMP007", "Arjun Desai",      "Engineering"),
    ("EMP008", "Pooja Joshi",      "HR"),
]

statuses  = ["present","present","present","present","late","absent","half-day"]
today     = datetime.today()

records_added = 0
for emp_id, name, dept in employees:
    for days_back in range(30):           # last 30 days
        d = today - timedelta(days=days_back)
        if d.weekday() >= 5: continue      # skip weekends
        status   = random.choice(statuses)
        time_in  = f"{random.randint(8,10):02d}:{random.randint(0,59):02d}:00"
        time_out = f"{random.randint(17,19):02d}:{random.randint(0,59):02d}:00"
        r = requests.post(URL, json={
            "emp_id":     emp_id,
            "name":       name,
            "department": dept,
            "date":       d.strftime("%Y-%m-%d"),
            "time_in":    time_in  if status != "absent" else "",
            "time_out":   time_out if status not in ("absent","half-day") else "",
            "status":     status,
        })
        if r.status_code == 201:
            records_added += 1

print(f"✅ Seeded {records_added} attendance records.")
