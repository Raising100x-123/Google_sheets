import gspread
from google.oauth2.service_account import Credentials
from pymongo import MongoClient
import os
import json
from dotenv import load_dotenv
import io
import sys

# Load environment variables
load_dotenv()

# MongoDB Setup
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("❌ Error: MONGO_URI environment variable is not set")
    sys.exit(1)

# Google Sheets credentials setup
# First check if credentials are provided as a string in environment variable
GOOGLE_SHEET_CREDENTIALS = os.getenv("GOOGLE_SHEET_CREDENTIALS")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "google-credentials.json")

# Print debug info (will appear in Render logs)
print(f"💡 Debug - MONGO_URI exists: {bool(MONGO_URI)}")
print(f"💡 Debug - GOOGLE_SHEET_CREDENTIALS exists: {bool(GOOGLE_SHEET_CREDENTIALS)}")
print(f"💡 Debug - SERVICE_ACCOUNT_FILE path: {SERVICE_ACCOUNT_FILE}")

# Setup Google credentials
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

try:
    # If credentials are provided as environment variable string
    if GOOGLE_SHEET_CREDENTIALS:
        # Method 1: Write to file then use from_service_account_file
        try:
            with open(SERVICE_ACCOUNT_FILE, 'w') as f:
                f.write(GOOGLE_SHEET_CREDENTIALS)
            print(f"✅ Created credentials file at {SERVICE_ACCOUNT_FILE}")
            credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        except Exception as file_error:
            print(f"⚠️ Could not write credentials file: {file_error}")
            
            # Method 2: Use from_service_account_info directly
            try:
                service_account_info = json.loads(GOOGLE_SHEET_CREDENTIALS)
                credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
                print("✅ Created credentials from environment variable JSON string")
            except Exception as json_error:
                print(f"❌ Error parsing credentials JSON: {json_error}")
                sys.exit(1)
    # If the file already exists (local development)
    elif os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"✅ Using existing credentials file at {SERVICE_ACCOUNT_FILE}")
        credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    else:
        print("❌ Error: No Google credentials available. Set GOOGLE_SHEET_CREDENTIALS or provide a service account file.")
        sys.exit(1)
        
    # Google Sheets setup
    client = gspread.authorize(credentials)
    
    # Open Google Sheet - add error handling here
    try:
        spreadsheet = client.open("Lead_Data")
        sheet = spreadsheet.sheet1
        print("✅ Successfully connected to Google Sheet")
    except Exception as sheet_error:
        print(f"❌ Error opening Google Sheet: {sheet_error}")
        sys.exit(1)
        
except Exception as auth_error:
    print(f"❌ Error setting up Google authentication: {auth_error}")
    sys.exit(1)

# MongoDB connection
try:
    mongo_client = MongoClient(MONGO_URI)
    # Test the connection
    mongo_client.admin.command('ping')
    print("✅ Successfully connected to MongoDB")
    db = mongo_client["ChatbotDB"]
    collection = db["lead_data"]
except Exception as mongo_error:
    print(f"❌ Error connecting to MongoDB: {mongo_error}")
    sys.exit(1)

def find_row_by_session_id(session_id):
    try:
        records = sheet.get_all_records()
        for idx, record in enumerate(records, start=2):  # start=2 because header is in row 1
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
    except Exception as e:
        print(f"❌ Error in upsert_google_sheet: {e}")

# Main execution - MongoDB Change Stream
if __name__ == "__main__":
    print("⏳ Listening for MongoDB Changes...")

    try:
        with collection.watch(full_document='updateLookup') as stream:
            for change in stream:
                if change['operationType'] in ['insert', 'update', 'replace']:
                    doc = change['fullDocument']
                    upsert_google_sheet(doc)  # Update or insert the document into Google Sheet
    except Exception as e:
        print(f"❌ Error in change stream: {e}")
        sys.exit(1)