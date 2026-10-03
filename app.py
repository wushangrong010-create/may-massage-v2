# May Massage V2 backend skeleton
# This endpoint is intentionally separated from the phone page:
# Google credentials must stay on the server, never in the browser.
from flask import Flask, jsonify, send_from_directory
app=Flask(__name__, static_folder='.')
@app.get('/')
def home(): return send_from_directory('.', 'index.html')
@app.get('/api/appointments')
def appointments():
    # Production step: replace this test response with Google Calendar API retrieval.
    # The front end is already built to consume this standardized structure.
    return jsonify([
      {"customer":"Shawn","start":"2026-10-05T11:00:00-05:00","end":"2026-10-05T12:00:00-05:00","duration":60,"service":"Undecided","price":60},
      {"customer":"Shawn","start":"2026-10-05T13:00:00-05:00","end":"2026-10-05T14:30:00-05:00","duration":90,"service":"Oil Massage","price":90}
    ])
if __name__=='__main__': app.run(host='0.0.0.0',port=8000,debug=True)
