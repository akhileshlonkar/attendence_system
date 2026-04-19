"""
Attendance Record Storage System
Simulates HDFS  → local folder  : hdfs_store/
Simulates Cloud → local folder  : cloud_store/
SQLite database for fast queries : attendance.db

File Storage (Cloud SaaS over LAN):
  - Files are split into fixed-size blocks (64 KB each)
  - Each block is individually encrypted with Fernet (AES-128-CBC)
  - Encrypted blocks are stored in HDFS-style partitioned folders
  - Download reassembles and decrypts blocks on the fly
"""

import os, json, csv, sqlite3, io
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, send_file
from cryptography.fernet import Fernet

# ── paths ──────────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
HDFS_DIR    = os.path.join(BASE_DIR, "hdfs_store")   # simulates HDFS
CLOUD_DIR   = os.path.join(BASE_DIR, "cloud_store")  # simulates S3/GCS/Azure
DB_PATH     = os.path.join(BASE_DIR, "attendance.db")

BLOCK_SIZE  = 64 * 1024          # 64 KB per block
FILE_DIR    = os.path.join(HDFS_DIR, "files")   # encrypted blocks live here

os.makedirs(HDFS_DIR,  exist_ok=True)
os.makedirs(CLOUD_DIR, exist_ok=True)
os.makedirs(FILE_DIR,  exist_ok=True)

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
        # File storage tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                filename      TEXT    NOT NULL,
                original_size INTEGER NOT NULL,
                block_size    INTEGER NOT NULL,
                block_count   INTEGER NOT NULL,
                enc_key       TEXT    NOT NULL,
                created_at    TEXT    DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_blocks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id     INTEGER NOT NULL,
                block_index INTEGER NOT NULL,
                block_path  TEXT    NOT NULL,
                enc_size    INTEGER NOT NULL,
                FOREIGN KEY(file_id) REFERENCES files(id)
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


# ── File Storage routes ────────────────────────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Split file into 64 KB blocks, encrypt each with Fernet, store in HDFS."""
    if "file" not in request.files:
        return jsonify({"error": "No file field in request"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    data          = f.read()
    original_size = len(data)

    # Generate a unique Fernet key for this file
    key    = Fernet.generate_key()
    fernet = Fernet(key)

    # Split into fixed-size blocks
    blocks = [data[i : i + BLOCK_SIZE] for i in range(0, max(len(data), 1), BLOCK_SIZE)]

    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO files (filename, original_size, block_size, block_count, enc_key)
            VALUES (?, ?, ?, ?, ?)
        """, (f.filename, original_size, BLOCK_SIZE, len(blocks), key.decode()))
        file_id = cur.lastrowid

        for idx, block in enumerate(blocks):
            encrypted = fernet.encrypt(block)
            folder    = os.path.join(FILE_DIR, f"file_{file_id}", f"block_{idx}")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "data.enc")
            with open(path, "wb") as bfp:
                bfp.write(encrypted)
            conn.execute("""
                INSERT INTO file_blocks (file_id, block_index, block_path, enc_size)
                VALUES (?, ?, ?, ?)
            """, (file_id, idx, path, len(encrypted)))
        conn.commit()

    return jsonify({
        "message":       "File uploaded, split into blocks & encrypted",
        "file_id":       file_id,
        "filename":      f.filename,
        "original_size": original_size,
        "block_size":    BLOCK_SIZE,
        "block_count":   len(blocks),
    }), 201


@app.route("/api/download/<int:file_id>", methods=["GET"])
def download_file(file_id):
    """Decrypt and reassemble blocks, stream original file to client."""
    with get_db() as conn:
        meta   = conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
        if not meta:
            return jsonify({"error": "File not found"}), 404
        blocks = conn.execute(
            "SELECT * FROM file_blocks WHERE file_id=? ORDER BY block_index",
            (file_id,)
        ).fetchall()

    fernet = Fernet(meta["enc_key"].encode())
    buf    = io.BytesIO()
    for blk in blocks:
        with open(blk["block_path"], "rb") as bfp:
            buf.write(fernet.decrypt(bfp.read()))
    buf.seek(0)
    return send_file(buf, download_name=meta["filename"], as_attachment=True)


@app.route("/api/files", methods=["GET"])
def list_files():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, filename, original_size, block_size, block_count, created_at "
            "FROM files ORDER BY id DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/files/<int:file_id>", methods=["DELETE"])
def delete_file(file_id):
    with get_db() as conn:
        blocks = conn.execute(
            "SELECT block_path FROM file_blocks WHERE file_id=?", (file_id,)
        ).fetchall()
        for blk in blocks:
            try:
                os.remove(blk["block_path"])
            except FileNotFoundError:
                pass
        conn.execute("DELETE FROM file_blocks WHERE file_id=?", (file_id,))
        conn.execute("DELETE FROM files WHERE id=?", (file_id,))
        conn.commit()
    return jsonify({"message": f"File {file_id} deleted"})


if __name__ == "__main__":
    print("=" * 55)
    print("  Attendance System running at http://127.0.0.1:5000")
    print("  HDFS  store →", HDFS_DIR)
    print("  Cloud store →", CLOUD_DIR)
    print("  SQLite DB   →", DB_PATH)
    print("=" * 55)
    app.run(debug=True, port=5000)
