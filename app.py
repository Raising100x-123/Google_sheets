import os
import sys
import json
import gspread
from flask import Flask
from dotenv import load_dotenv
from pymongo import MongoClient
from google.oauth2.service_account import Credentials
import threading

# Load env
load_dotenv()

app = Flask(__name__)  # 👈 Required for gunicorn to find

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("❌ Error: MONGO_URI not set")
    sys.exit(1)

# Google Sheets Setup
GOOGLE_SHEET_CREDENTIALS = os.getenv("GOOGLE_SHEET_CREDENTIALS")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "google-credentials.json")

print(f"💡 MONGO_URI exists: {bool(MONGO_URI)}")
print(f"💡 GOOGLE_SHEET_CREDENTIALS exists: {bool(GOOGLE_SHEET_CREDENTIALS)}")

scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

try:
    if GOOGLE_SHEET_CREDENTIALS:
        with open(SERVICE_ACCOUNT_FILE, 'w') as f:
            f.write(GOOGLE_SHEET_CREDENTIALS)
        print(f"✅ Wrote credentials to {SERVICE_ACCOUNT_FILE}")
        credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    elif os.path.exists(SERVICE_ACCOUNT_FILE):
        credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    else:
        raise Exception("No credentials found")

    gspread_client = gspread.authorize(credentials)
    spreadsheet = gspread_client.open("Lead_Data")
    sheet = spreadsheet.sheet1
    print("✅ Connected to Google Sheet")
except Exception as e:
    print(f"❌ Google Auth Error: {e}")
    sys.exit(1)

try:
    mongo_client = MongoClient(MONGO_URI)
    mongo_client.admin.command('ping')
    db = mongo_client["ChatbotDB"]
    collection = db["lead_data"]
    print("✅ Connected to MongoDB")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")
    sys.exit(1)


def find_row_by_session_id(session_id):
    try:
        records = sheet.get_all_records()
        for idx, record in enumerate(records, start=2):
            if record.get('session_id') == session_id:
                return idx
        return None
    except Exception as e:
        print(f"❌ Find row error: {e}")
        return None


def upsert_google_sheet(doc):
    try:
        session_id = doc.get("session_id", "")
        contact_number = doc.get("contact_number", "")
        email_id = doc.get("email_id", "")
        location = doc.get("location", "")
        name = doc.get("name", "")
        service_interest = doc.get("service_interest", "")
        appointment_date = doc.get("Appointment_date", "")
        appointment_time = doc.get("Appointment_Time", "")

        all_rows = sheet.get_all_records()
        serial_number = len(all_rows) + 1

        row_data = [
            serial_number,
            session_id,
            contact_number,
            email_id,
            location,
            name,
            service_interest,
            appointment_date,
            appointment_time,
        ]

        row_number = find_row_by_session_id(session_id)
        if row_number:
            sheet.update(f'A{row_number}:I{row_number}', [row_data])
            print(f"✅ Updated session_id {session_id}")
        else:
            sheet.append_row(row_data)
            print(f"✅ Inserted session_id {session_id}")
    except Exception as e:
        print(f"❌ Upsert error: {e}")


def watch_changes():
    print("⏳ Watching MongoDB...")
    try:
        with collection.watch(full_document='updateLookup') as stream:
            for change in stream:
                if change['operationType'] in ['insert', 'update', 'replace']:
                    doc = change['fullDocument']
                    upsert_google_sheet(doc)
    except Exception as e:
        print(f"❌ Change stream error: {e}")
        sys.exit(1)


# 🔁 Run the change stream watcher in a separate thread
@app.before_first_request
def start_background_thread():
    thread = threading.Thread(target=watch_changes)
    thread.daemon = True
    thread.start()

# 🧪 A simple route for Render health check
@app.route('/')
def index():
    return "✅ Server is running and connected!"

