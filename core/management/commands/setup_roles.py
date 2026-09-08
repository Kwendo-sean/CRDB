from django.contrib.auth.models import Group,Permission
from django.core.management.base import BaseCommand
ROLES={"Super Admin":None,"Event Admin":["add_participant","change_participant","view_participant","add_session","change_session","view_session","add_attendance","change_attendance","view_attendance","view_quizattempt"],"Check-in Staff":["view_participant","add_attendance","view_attendance","view_session"],"Quiz Facilitator":["view_participant","view_quiz","change_quiz","view_question","change_question","view_quizattempt","view_quizresponse"],"Analytics Viewer":["view_participant","view_session","view_attendance","view_quizattempt","view_quizresponse","view_scoretransaction"]}
class Command(BaseCommand):
 help="Create idempotent Learning Week admin roles."
 def handle(self,*args,**opts):
  for name,codenames in ROLES.items():
   group,_=Group.objects.get_or_create(name=name)
   if codenames is not None: group.permissions.set(Permission.objects.filter(content_type__app_label="core",codename__in=codenames))
  self.stdout.write(self.style.SUCCESS("Roles ready"))
