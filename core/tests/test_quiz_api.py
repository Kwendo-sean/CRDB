import json,uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from core.models import AnswerChoice,Participant,Question,Quiz,QuizAttempt,QuizResponse

class QuizApiTests(TestCase):
 def setUp(self):
  self.p=Participant.objects.create(full_name="Grace",staff_id="G1")
  self.quiz=Quiz.objects.create(day=1,title="Official",sequence=1,state="question_open")
  self.q=Question.objects.create(quiz=self.quiz,number=1,text="Official Q",time_limit_seconds=20,base_points=1000,is_open=True,opened_at=timezone.now(),closes_at=timezone.now()+timezone.timedelta(seconds=20))
  self.c=AnswerChoice.objects.create(question=self.q,number=1,text="A",is_correct=True)
  for n in range(2,5): AnswerChoice.objects.create(question=self.q,number=n,text=str(n))
  session=self.client.session; session["participant_id"]=str(self.p.id); session.save()
 def test_join_and_submit_answer_maps_to_participant(self):
  join=self.client.post(reverse("quiz-join",args=[self.quiz.id])); self.assertEqual(join.status_code,302)
  attempt=QuizAttempt.objects.get(participant=self.p,quiz=self.quiz)
  answer=self.client.post(reverse("quiz-answer",args=[self.quiz.id]),data=json.dumps({"question_id":self.q.id,"choice_id":self.c.id,"submission_id":str(uuid.uuid4()),"response_duration_ms":1500}),content_type="application/json")
  self.assertEqual(answer.status_code,201); self.assertEqual(answer.json()["competition_points"],1000)
  self.assertNotIn("explanation",answer.json())
  self.assertEqual(attempt.responses.get().attempt.participant,self.p)
 def test_participant_cannot_answer_closed_question(self):
  QuizAttempt.objects.create(participant=self.p,quiz=self.quiz)
  self.q.is_open=False; self.q.save()
  answer=self.client.post(reverse("quiz-answer",args=[self.quiz.id]),data=json.dumps({"question_id":self.q.id,"choice_id":self.c.id,"submission_id":str(uuid.uuid4()),"response_duration_ms":1500}),content_type="application/json")
  self.assertEqual(answer.status_code,409)
 def test_current_state_restores_open_question_without_revealing_the_answer(self):
  self.quiz.current_question=self.q; self.quiz.save(update_fields=["current_question"])
  self.client.post(reverse("quiz-join",args=[self.quiz.id]))
  response=self.client.get(reverse("quiz-state",args=[self.quiz.id]))
  self.assertEqual(response.status_code,200)
  payload=response.json()
  self.assertEqual(payload["state"],Quiz.State.QUESTION_OPEN)
  self.assertEqual(payload["question"]["id"],self.q.id)
  self.assertEqual(len(payload["question"]["choices"]),4)
  self.assertNotIn("is_correct",payload["question"]["choices"][0])
  self.assertFalse(payload["answered"])
  self.assertIn("server_time",payload)

class FacilitatorTests(TestCase):
 def test_staff_can_open_question_and_server_sets_deadline(self):
  admin=get_user_model().objects.create_user("host",password="pass",is_staff=True); self.client.login(username="host",password="pass")
  quiz=Quiz.objects.create(day=1,title="Official",sequence=1,state=Quiz.State.SCHEDULED)
  q=Question.objects.create(quiz=quiz,number=1,text="Q",time_limit_seconds=20,base_points=1000)
  response=self.client.post(reverse("quiz-control-action",args=[quiz.id]),{"action":"open_question","question_id":q.id})
  self.assertRedirects(response,reverse("quiz-control",args=[quiz.id])); q.refresh_from_db(); self.assertTrue(q.is_open); self.assertIsNotNone(q.closes_at)
 def test_draft_round_cannot_be_launched_before_publication(self):
  get_user_model().objects.create_user("host2",password="pass",is_staff=True); self.client.login(username="host2",password="pass")
  quiz=Quiz.objects.create(day=1,title="Unvalidated",sequence=9,state=Quiz.State.DRAFT)
  q=Question.objects.create(quiz=quiz,number=1,text="Q",time_limit_seconds=20,base_points=1000)
  self.client.post(reverse("quiz-control-action",args=[quiz.id]),{"action":"open_question","question_id":q.id})
  q.refresh_from_db(); quiz.refresh_from_db()
  self.assertFalse(q.is_open); self.assertEqual(quiz.state,Quiz.State.DRAFT)
 def test_staff_control_screen_shows_per_answer_live_counts(self):
  admin=get_user_model().objects.create_user("host",password="pass",is_staff=True); self.client.login(username="host",password="pass")
  participant=Participant.objects.create(full_name="Grace",staff_id="G2")
  quiz=Quiz.objects.create(day=2,title="Data Detective",sequence=1,state=Quiz.State.QUESTION_OPEN)
  question=Question.objects.create(quiz=quiz,number=1,text="Find the signal",time_limit_seconds=20,base_points=1000,is_open=True)
  choice=AnswerChoice.objects.create(question=question,number=1,text="Signal A",is_correct=True)
  for number in range(2,5): AnswerChoice.objects.create(question=question,number=number,text=f"Signal {number}")
  attempt=QuizAttempt.objects.create(participant=participant,quiz=quiz)
  QuizResponse.objects.create(attempt=attempt,question=question,selected_choice=choice,submission_id=uuid.uuid4(),is_correct=True,base_points_awarded=1000,response_duration_ms=900)
  quiz.current_question=question; quiz.save(update_fields=["current_question"])
  response=self.client.get(reverse("quiz-control",args=[quiz.id]))
  self.assertContains(response,"A / 1")
  self.assertContains(response,"ANSWERS IN")
  self.assertContains(response,"Find the signal")
