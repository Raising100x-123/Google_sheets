import gspread
from google.oauth2.service_account import Credentials
from pymongo import MongoClient
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create service account file from environment variable if needed
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "temp-credentials.json")
GOOGLE_SHEET_CREDENTIALS = os.getenv("GOOGLE_SHEET_CREDENTIALS")

if GOOGLE_SHEET_CREDENTIALS:
    # Ensure directory exists if it's a path with directories
    directory = os.path.dirname(SERVICE_ACCOUNT_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)
    
    # Write credentials to file
    with open(SERVICE_ACCOUNT_FILE, 'w') as f:
        f.write(GOOGLE_SHEET_CREDENTIALS)

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["ChatbotDB"]
collection = db["lead_data"]

# Google Sheet Setup
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
client = gspread.authorize(credentials)

# Open Google Sheet
spreadsheet = client.open("Lead_Data")
sheet = spreadsheet.sheet1

def find_row_by_session_id(session_id):
    records = sheet.get_all_records()
    for idx, record in enumerate(records, start=2):  # start=2 because header is in row 1
        if record.get('session_id') == session_id:
            return idx
    return None

def upsert_google_sheet(doc):
    session_id = doc.get("session_id", "")
    contact_number = doc.get("contact_number", "")
    email_id = doc.get("email_id", "")
    location = doc.get("location", "")
    name = doc.get("name", "")
    service_interest = doc.get("service_interest", "")
    appointment_date = doc.get("Appointment_date", "")
    appointment_Time = doc.get("Appointment_Time", "")
    

    # Generate serial number (S.no) based on the number of rows in the sheet
    all_rows = sheet.get_all_records()
    serial_number = len(all_rows) + 1  # Auto-increment based on the current number of rows

    row_data = [
        serial_number,  # Auto-generated serial number
        session_id,
        contact_number,
        email_id,
        location,
        name,
        service_interest,
        appointment_date,
        appointment_Time,
    ]

    row_number = find_row_by_session_id(session_id)
    
    if row_number:
        # Update existing row
        sheet.update(f'A{row_number}:I{row_number}', [row_data])
        print(f"✅ Updated session_id {session_id} at row {row_number}")
    else:
        # Insert new row
        sheet.append_row(row_data)
        print(f"✅ Inserted new session_id {session_id}")

# MongoDB Change Stream
print("⏳ Listening for MongoDB Changes...")

try:
    with collection.watch(full_document='updateLookup') as stream:
        for change in stream:
            if change['operationType'] in ['insert', 'update', 'replace']:
                doc = change['fullDocument']
                upsert_google_sheet(doc)  # Update or insert the document into Google Sheet
except Exception as e:
    print(f"Error in change stream: {e}")
    # In a production environment, you would want better error handling and possibly restart logic