"""
Attendance Record Storage System
Simulates HDFS  → local folder  : hdfs_store/
Simulates Cloud → local folder  : cloud_store/
SQLite database for fast queries : attendance.db
"""

import os, json, csv, sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for

# ── paths ──────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
HDFS_DIR    = os.path.join(BASE_DIR, "hdfs_store")   # simulates HDFS
CLOUD_DIR   = os.path.join(BASE_DIR, "cloud_store")  # simulates S3/GCS/Azure
DB_PATH     = os.path.join(BASE_DIR, "attendance.db")

os.makedirs(HDFS_DIR,  exist_ok=True)
os.makedirs(CLOUD_DIR, exist_ok=True)

# ── Flask ──────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── SQLite helpers ─────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                emp_id      TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                department  TEXT,
                date        TEXT    NOT NULL,
                time_in     TEXT,
                time_out    TEXT,
                status      TEXT    DEFAULT 'present',
                created_at  TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

init_db()

# ── Storage helpers ────────────────────────────────────────────────────────
def save_to_hdfs(record: dict):
    """Append a JSON line to a date-partitioned file (like HDFS partition)."""
    date  = record.get("date", datetime.now().strftime("%Y-%m-%d"))
    year, month, day = date.split("-")
    folder = os.path.join(HDFS_DIR, f"year={year}", f"month={month}", f"day={day}")
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, "data.jsonl")
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def save_to_cloud(record: dict):
    """Write individual JSON object to cloud store (simulates blob upload)."""
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    folder = os.path.join(CLOUD_DIR, record.get("department", "general").replace(" ", "_"))
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, f"{record['emp_id']}_{ts}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

def save_record(data: dict):
    """Write to SQLite + HDFS + Cloud."""
    with get_db() as conn:
        conn.execute("""
            INSERT INTO attendance (emp_id, name, department, date, time_in, time_out, status)
            VALUES (:emp_id, :name, :department, :date, :time_in, :time_out, :status)
        """, data)
        conn.commit()
    save_to_hdfs(data)
    save_to_cloud(data)

# ── API routes ─────────────────────────────────────────────────────────────
@app.route("/api/attendance", methods=["POST"])
def add_attendance():
    body = request.get_json(force=True)
    required = ["emp_id", "name", "date"]
    if not all(k in body for k in required):
        return jsonify({"error": f"Required fields: {required}"}), 400

    record = {
        "emp_id":     body["emp_id"],
        "name":       body["name"],
        "department": body.get("department", "General"),
        "date":       body["date"],
        "time_in":    body.get("time_in",  datetime.now().strftime("%H:%M:%S")),
        "time_out":   body.get("time_out", ""),
        "status":     body.get("status", "present"),
    }
    save_record(record)
    return jsonify({"message": "Attendance recorded", "record": record}), 201


@app.route("/api/attendance", methods=["GET"])
def list_attendance():
    emp_id = request.args.get("emp_id")
    date   = request.args.get("date")
    dept   = request.args.get("department")
    limit  = int(request.args.get("limit", 100))

    query  = "SELECT * FROM attendance WHERE 1=1"
    params = []
    if emp_id: query += " AND emp_id=?";     params.append(emp_id)
    if date:   query += " AND date=?";        params.append(date)
    if dept:   query += " AND department=?";  params.append(dept)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/summary", methods=["GET"])
def summary():
    with get_db() as conn:
        total      = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
        today      = datetime.now().strftime("%Y-%m-%d")
        today_cnt  = conn.execute("SELECT COUNT(*) FROM attendance WHERE date=?", (today,)).fetchone()[0]
        depts      = conn.execute(
            "SELECT department, COUNT(*) as cnt FROM attendance GROUP BY department"
        ).fetchall()
        monthly    = conn.execute(
            "SELECT substr(date,1,7) as month, COUNT(*) as cnt "
            "FROM attendance GROUP BY month ORDER BY month DESC LIMIT 6"
        ).fetchall()
    return jsonify({
        "total_records":    total,
        "today_records":    today_cnt,
        "by_department":    [dict(r) for r in depts],
        "last_6_months":    [dict(r) for r in monthly],
    })


@app.route("/api/attendance/<int:rec_id>", methods=["DELETE"])
def delete_record(rec_id):
    with get_db() as conn:
        conn.execute("DELETE FROM attendance WHERE id=?", (rec_id,))
        conn.commit()
    return jsonify({"message": f"Record {rec_id} deleted"})


@app.route("/api/export/csv", methods=["GET"])
def export_csv():
    """Export all records as CSV downloaded to client."""
    from flask import Response
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM attendance ORDER BY date DESC").fetchall()
    def generate():
        cols = ["id","emp_id","name","department","date","time_in","time_out","status","created_at"]
        yield ",".join(cols) + "\n"
        for r in rows:
            yield ",".join(str(r[c]) for c in cols) + "\n"
    return Response(generate(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=attendance.csv"})


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ── Dashboard (HTML) ────────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit_form():
    record = {
        "emp_id":     request.form["emp_id"],
        "name":       request.form["name"],
        "department": request.form.get("department", "General"),
        "date":       request.form["date"],
        "time_in":    request.form.get("time_in") or datetime.now().strftime("%H:%M:%S"),
        "time_out":   request.form.get("time_out", ""),
        "status":     request.form.get("status", "present"),
    }
    save_record(record)
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    print("=" * 55)
    print("  Attendance System running at http://127.0.0.1:5000")
    print("  HDFS  store →", HDFS_DIR)
    print("  Cloud store →", CLOUD_DIR)
    print("  SQLite DB   →", DB_PATH)
    print("=" * 55)
    app.run(debug=True, port=5000)
