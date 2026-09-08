from io import BytesIO
from django.core.exceptions import ValidationError
from django.test import TestCase
from openpyxl import Workbook
from core.importers import import_quiz_workbook
from core.models import Quiz

HEADERS=["day","challenge_name","question_number","question_text","answer_1","answer_2","answer_3","answer_4","correct_answer_number","time_limit","points","host_note"]
def workbook(rows):
    wb=Workbook(); ws=wb.active; ws.append(HEADERS)
    for row in rows: ws.append(row)
    stream=BytesIO(); wb.save(stream); stream.seek(0); return stream
class QuizImportTests(TestCase):
    def test_rejects_round_that_does_not_have_exactly_ten_questions(self):
        row=[1,"AI Infrastructure Trivia Sprint",1,"Q?","A","B","C","D",1,20,1000,"Note"]
        with self.assertRaisesMessage(ValidationError,"exactly 10"):
            import_quiz_workbook(workbook([row]))
        self.assertEqual(Quiz.objects.count(),0)
    def test_imports_exact_source_rows_atomically(self):
        rows=[[1,"AI Infrastructure Trivia Sprint",n,f"Official Q{n}","A","B","C","D",1,20,1000,f"Host {n}"] for n in range(1,11)]
        summary=import_quiz_workbook(workbook(rows))
        quiz=Quiz.objects.get(); self.assertEqual(summary["questions"],10)
        self.assertEqual(quiz.questions.get(number=4).text,"Official Q4")
        self.assertEqual(quiz.questions.get(number=4).choices.count(),4)
