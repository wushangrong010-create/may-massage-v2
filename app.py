import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder=".")

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    customer TEXT NOT NULL,
                    phone TEXT,
                    start_time TIMESTAMPTZ NOT NULL,
                    duration INTEGER NOT NULL,
                    service TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)


@app.get("/")
def home():
    return send_from_directory(".", "index.html")

@app.get("/booking")
def booking():
    return send_from_directory(".", "booking.html")
@app.route("/api/appointments", methods=["GET", "POST"])
def handle_appointments():
    if request.method == "GET":
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, customer, phone, start_time,
                           duration, service
                    FROM appointments
                    ORDER BY start_time
                """)
                rows = cur.fetchall()

        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "customer": row["customer"],
                "phone": row["phone"],
                "start": row["start_time"].astimezone(ZoneInfo("America/Winnipeg")).isoformat(),
                "duration": row["duration"],
                "service": row["service"],
                "price": row["duration"]
            })

        return jsonify(result)

    data = request.get_json(silent=True) or {}

    customer = str(data.get("customer", "")).strip()
    phone = str(data.get("phone", "")).strip()
    start = str(data.get("start", "")).strip()
    service = str(data.get("service", "")).strip()

    try:
        duration = int(data.get("duration", 0))
    except (TypeError, ValueError):
        duration = 0

    if not customer or not start or not service:
        return jsonify({
            "error": "customer, start and service are required"
        }), 400

    if duration < 60 or duration % 10 != 0:
        return jsonify({
            "error": "duration must be at least 60 minutes and use 10-minute increments"
        }), 400

    try:
        start_time = datetime.fromisoformat(start)
    except ValueError:
        return jsonify({
            "error": "invalid start date/time"
        }), 400

    with get_db() as conn:
        with conn.cursor() as cur:
                        
            cur.execute("SELECT pg_advisory_xact_lock(20261008)")

            cur.execute("""
                SELECT id
                FROM appointments
                WHERE start_time < %s + (%s * INTERVAL '1 minute')
                  AND start_time + (duration * INTERVAL '1 minute') > %s
                LIMIT 1
            """, (start_time, duration, start_time))

            if cur.fetchone():
                return jsonify({
                    "ok": False,
                    "error": "This time is already booked. Please choose another time."
                }), 409            
            cur.execute("""
                INSERT INTO appointments
                    (customer, phone, start_time, duration, service)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (
                customer,
                phone,
                start_time,
                duration,
                service
            ))
            appointment_id = cur.fetchone()["id"]
        conn.commit()
    
    return jsonify({
        "ok": True,
        "id": appointment_id
    }), 201

@app.route("/api/appointments/<int:appointment_id>", methods=["DELETE"])
def cancel_appointment(appointment_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM appointments WHERE id = %s RETURNING id",
                (appointment_id,)
            )
            deleted = cur.fetchone()

            if not deleted:
                return jsonify({
                    "ok": False,
                    "error": "Appointment not found"
                }), 404

            conn.commit()

    return jsonify({
        "ok": True,
        "id": appointment_id
    })
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
