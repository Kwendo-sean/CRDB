import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
SCOPES=["https://www.googleapis.com/auth/spreadsheets.readonly"]
def fetch_google_sheet_rows(source,credential_file=None):
 path=credential_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
 if not path: raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE is required")
 credentials=service_account.Credentials.from_service_account_file(path,scopes=SCOPES)
 service=build("sheets","v4",credentials=credentials,cache_discovery=False)
 response=service.spreadsheets().values().get(spreadsheetId=source.spreadsheet_id,range=f"'{source.worksheet_name}'").execute()
 values=response.get("values",[])
 if not values: return []
 headers=[str(x).strip() for x in values[0]]
 return [dict(zip(headers,row)) for row in values[1:] if any(str(x).strip() for x in row)]
