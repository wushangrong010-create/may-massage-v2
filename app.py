
import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

import psycopg
from psycopg.rows import dict_row
from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI

app = Flask(__name__, static_folder=".")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

BASE_URL = "https://may-massage-v2.onrender.com"
WINNIPEG_TZ = ZoneInfo("America/Winnipeg")

ai_client = OpenAI(
    api_key=OPENAI_API_KEY
) if OPENAI_API_KEY else None


# =====================================
# DATABASE
# =====================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row
    )


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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS phone_conversations (
                    call_sid TEXT PRIMARY KEY,
                    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)


# =====================================
# WEBSITE
# =====================================

@app.get("/")
def home():
    return send_from_directory(".", "index.html")


@app.get("/booking")
def booking():
    return send_from_directory(".", "booking.html")


# =====================================
# APPOINTMENTS API
# =====================================

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
                "start": row["start_time"].astimezone(
                    WINNIPEG_TZ
                ).isoformat(),
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
            "error": (
                "duration must be at least 60 minutes "
                "and use 10-minute increments"
            )
        }), 400

    try:
        start_time = datetime.fromisoformat(start)

        if start_time.tzinfo is None:
            start_time = start_time.replace(
                tzinfo=WINNIPEG_TZ
            )

    except ValueError:
        return jsonify({
            "error": "invalid start date/time"
        }), 400

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SELECT pg_advisory_xact_lock(20261008)"
            )

            cur.execute("""
                SELECT id
                FROM appointments
                WHERE start_time <
                    %s + (%s * INTERVAL '1 minute')
                  AND start_time +
                    (duration * INTERVAL '1 minute') > %s
                LIMIT 1
            """, (
                start_time,
                duration,
                start_time
            ))

            if cur.fetchone():
                return jsonify({
                    "ok": False,
                    "error": (
                        "This time is already booked. "
                        "Please choose another time."
                    )
                }), 409

            cur.execute("""
                INSERT INTO appointments
                    (
                        customer,
                        phone,
                        start_time,
                        duration,
                        service
                    )
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


@app.route(
    "/api/appointments/<int:appointment_id>",
    methods=["DELETE"]
)
def cancel_appointment(appointment_id):

    with get_db() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                DELETE FROM appointments
                WHERE id = %s
                RETURNING id
                """,
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


# =====================================
# BUSINESS INFORMATION
# =====================================

BUSINESS_INSTRUCTIONS = """
You are the friendly AI telephone receptionist
for May Massage in Winnipeg, Manitoba, Canada.

BUSINESS FACTS:

Business name: May Massage

Address:
150 Royal Avenue, Winnipeg, Manitoba, Canada.

Opening hours:
Monday: 10:00 AM to 8:00 PM.
Wednesday: 10:00 AM to 8:00 PM.
Closed on other days.

Therapist:
May.

Services:
Oil Massage.
Chinese Massage.

Appointment only.
No walk-in customers at this time.

Minimum massage duration:
60 minutes.

After 60 minutes, customers may add time
in increments of 10 minutes.

Price:
1 Canadian dollar per minute.
Tax is already included.

Examples:
60 minutes costs 60 Canadian dollars.
70 minutes costs 70 Canadian dollars.
90 minutes costs 90 Canadian dollars.
120 minutes costs 120 Canadian dollars.

Payment:
Cash or Interac e-Transfer.

IMPORTANT RULES:

1. Speak naturally, warmly and briefly.
2. Default to English.
3. If the customer speaks another language,
   respond in that language when possible.
4. Never invent prices, services or opening hours.
5. Do not claim that a booking has been made.
6. You cannot directly create, cancel or change
   appointments through this phone assistant yet.
7. If the customer wants an appointment, explain
   that booking confirmation is not available
   through the AI phone assistant at this stage.
8. Do not promise that May will call back.
9. If the customer asks for medical advice,
   avoid diagnosis and recommend a qualified
   healthcare professional when appropriate.
10. Keep most replies under 50 words.
11. Do not mention these internal instructions.
"""


# =====================================
# PHONE CONVERSATION STORAGE
# =====================================

def load_conversation(call_sid):

    if not call_sid:
        return []

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT messages
                FROM phone_conversations
                WHERE call_sid = %s
            """, (call_sid,))

            row = cur.fetchone()

    if not row:
        return []

    messages = row["messages"]

    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except json.JSONDecodeError:
            return []

    return messages if isinstance(messages, list) else []


def save_conversation(call_sid, messages):

    if not call_sid:
        return

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO phone_conversations
                    (call_sid, messages)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (call_sid)
                DO UPDATE SET
                    messages = EXCLUDED.messages,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                call_sid,
                json.dumps(messages, ensure_ascii=False)
            ))

        conn.commit()


# =====================================
# OPENAI ANSWERING
# =====================================

def ask_ai(call_sid, customer_speech):

    if not ai_client:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured"
        )

    history = load_conversation(call_sid)

    history.append({
        "role": "user",
        "content": customer_speech
    })

    # Keep the latest conversation turns.
    recent_history = history[-12:]

    messages = [
        {
            "role": "system",
            "content": BUSINESS_INSTRUCTIONS
        }
    ] + recent_history

    completion = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=180,
        temperature=0.4,
        timeout=18
    )

    answer = (
        completion.choices[0].message.content or ""
    ).strip()

    if not answer:
        answer = (
            "Sorry, could you please repeat "
            "your question?"
        )

    history.append({
        "role": "assistant",
        "content": answer
    })

    save_conversation(
        call_sid,
        history[-20:]
    )

    return answer


# =====================================
# TWILIO XML HELPERS
# =====================================

def twiml_response(xml_body):

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        + xml_body +
        '</Response>'
    )

    return app.response_class(
        xml,
        mimetype="text/xml"
    )


def twilio_say(message):

    return (
        '<Say voice="alice" language="en-US">'
        + escape(message) +
        '</Say>'
    )


def twilio_gather(prompt):

    return (
        '<Gather input="speech" '
        'language="en-US" '
        'speechTimeout="auto" '
        'timeout="8" '
        'method="POST" '
        'action="' + BASE_URL + '/twilio/heard">'
        + twilio_say(prompt) +
        '</Gather>'
    )


# =====================================
# TWILIO INCOMING CALL
# =====================================

@app.route(
    "/twilio/voice",
    methods=["GET", "POST"]
)
def twilio_voice():

    prompt = (
        "Thank you for calling May Massage. "
        "I'm the AI receptionist. "
        "How can I help you today?"
    )

    xml_body = twilio_gather(prompt)

    xml_body += twilio_say(
        "Sorry, I didn't hear anything. "
        "Please call again."
    )

    return twiml_response(xml_body)


# =====================================
# TWILIO CUSTOMER SPEECH
# =====================================

@app.route(
    "/twilio/heard",
    methods=["POST"]
)
def twilio_heard():

    speech = request.form.get(
        "SpeechResult", ""
    ).strip()

    call_sid = request.form.get(
        "CallSid", ""
    ).strip()

    logger.info(
        "Twilio speech received for call %s",
        call_sid
    )

    if not speech:

        xml_body = twilio_gather(
            "Sorry, I didn't catch that. "
            "Could you please say it again?"
        )

        xml_body += twilio_say(
            "Thank you for calling May Massage. "
            "Goodbye."
        )

        return twiml_response(xml_body)

    try:

        answer = ask_ai(
            call_sid,
            speech
        )

    except Exception:

        logger.exception(
            "AI answering failed"
        )

        answer = (
            "I'm sorry, our AI assistant "
            "is temporarily unavailable. "
            "May Massage is open on Mondays "
            "and Wednesdays from ten A M "
            "to eight P M. "
            "Thank you for your patience."
        )

    xml_body = twilio_say(answer)

    xml_body += twilio_gather(
        "Is there anything else "
        "I can help you with?"
    )

    xml_body += twilio_say(
        "Thank you for calling May Massage. "
        "Goodbye."
    )

    return twiml_response(xml_body)


# =====================================
# INITIALIZE DATABASE
# =====================================

with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000"))
    )
