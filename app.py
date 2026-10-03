from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder='.')

appointments = []

@app.get('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/api/appointments', methods=['GET', 'POST'])
def handle_appointments():
    if request.method == 'GET':
        return jsonify(appointments)

    data = request.get_json(silent=True) or {}

    customer = data.get('customer')
    start = data.get('start')
    duration = data.get('duration', 60)
    service = data.get('service', 'Undecided')

    if not customer or not start:
        return jsonify({"error": "customer and start are required"}), 400

    appointment = {
        "customer": customer,
        "start": start,
        "duration": int(duration),
        "service": service,
        "price": int(duration)
    }

    appointments.append(appointment)

    return jsonify(appointment), 201

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
