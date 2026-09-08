from io import BytesIO
from django.test import TestCase
from openpyxl import Workbook
from core.importers import import_session_workbook
from core.models import Session

class SessionImportTests(TestCase):
 def test_imports_exact_session_content(self):
  wb=Workbook(); ws=wb.active
  ws.append(["source_key","day","date","start_time","end_time","title","facilitator","format","audience","location"])
  ws.append(["D1-S1",1,"2026-09-07","14:00","16:00","Exact Official Title","Pascal Aloo","FACE-TO-FACE","Operations","HQ"])
  stream=BytesIO(); wb.save(stream); stream.seek(0)
  summary=import_session_workbook(stream)
  session=Session.objects.get()
  self.assertEqual(summary["sessions"],1); self.assertEqual(session.title,"Exact Official Title"); self.assertEqual(session.facilitator,"Pascal Aloo")
