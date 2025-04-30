import os
import sys
import json
import threading
from dotenv import load_dotenv
from flask import Flask
from pymongo import MongoClient
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
load_dotenv()

# === Flask app ===
app = Flask(__name__)

# === MongoDB Setup ===
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("❌ Error: MONGO_URI environment variable is not set")
    sys.exit(1)

# === Google Sheet Setup ===
GOOGLE_SHEET_CREDENTIALS = os.getenv("GOOGLE_SHEET_CREDENTIALS")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "google-credentials.json")

# Debug logs
print(f"💡 Debug - MONGO_URI exists: {bool(MONGO_URI)}")
print(f"💡 Debug - GOOGLE_SHEET_CREDENTIALS exists: {bool(GOOGLE_SHEET_CREDENTIALS)}")
print(f"💡 Debug - SERVICE_ACCOUNT_FILE path: {SERVICE_ACCOUNT_FILE}")

scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

try:
    if GOOGLE_SHEET_CREDENTIALS:
        try:
            with open(SERVICE_ACCOUNT_FILE, 'w') as f:
                f.write(GOOGLE_SHEET_CREDENTIALS)
            print(f"✅ Created credentials file at {SERVICE_ACCOUNT_FILE}")
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        except Exception as file_error:
            print(f"⚠️ Could not write credentials file: {file_error}")
            try:
                service_account_info = json.loads(GOOGLE_SHEET_CREDENTIALS)
                credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
                print("✅ Created credentials from environment variable JSON string")
            except Exception as json_error:
                print(f"❌ Error parsing credentials JSON: {json_error}")
                sys.exit(1)
    elif os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"✅ Using existing credentials file at {SERVICE_ACCOUNT_FILE}")
        credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    else:
        print("❌ Error: No Google credentials available.")
        sys.exit(1)

    client = gspread.authorize(credentials)
    spreadsheet = client.open("Lead_Data")
    sheet = spreadsheet.sheet1
    print("✅ Successfully connected to Google Sheet")

except Exception as auth_error:
    print(f"❌ Error setting up Google authentication: {auth_error}")
    sys.exit(1)

# === MongoDB connection ===
try:
    mongo_client = MongoClient(MONGO_URI)
    mongo_client.admin.command('ping')
    print("✅ Successfully connected to MongoDB")
    db = mongo_client["ChatbotDB"]
    collection = db["lead_data"]
except Exception as mongo_error:
    print(f"❌ Error connecting to MongoDB: {mongo_error}")
    sys.exit(1)

# === Helper functions ===
def find_row_by_session_id(session_id):
    try:
        records = sheet.get_all_records()
        for idx, record in enumerate(records, start=2):
            if record.get('session_id') == session_id:
                return idx
        return None
    except Exception as e:
        print(f"❌ Error finding row: {e}")
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
            print(f"✅ Updated session_id {session_id} at row {row_number}")
        else:
            sheet.append_row(row_data)
            print(f"✅ Inserted new session_id {session_id}")
    except Exception as e:
        print(f"❌ Error in upsert_google_sheet: {e}")

# === Change Stream Watcher ===
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

# Start background thread on first request
@app.before_first_request
def start_background_thread():
    thread = threading.Thread(target=watch_changes)
    thread.daemon = True
    thread.start()

# Simple route to verify deployment
@app.route("/")
def index():
    return "✅ Flask app is running. MongoDB and Google Sheet are connected."

