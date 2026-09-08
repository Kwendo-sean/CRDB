from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from .models import Participant,Quiz

class QuizConsumer(AsyncJsonWebsocketConsumer):
 async def connect(self):
  user=self.scope.get("user")
  participant_id=self.scope.get("session",{}).get("participant_id")
  self.group=None
  if not await self.can_subscribe(user,participant_id,self.scope["url_route"]["kwargs"]["quiz_id"]):
   await self.close(code=4401)
   return
  self.quiz_id=self.scope["url_route"]["kwargs"]["quiz_id"]
  self.group=f"quiz_{self.quiz_id}"
  await self.channel_layer.group_add(self.group,self.channel_name)
  await self.accept()
 async def disconnect(self,code):
  if self.group: await self.channel_layer.group_discard(self.group,self.channel_name)
 async def quiz_state(self,event): await self.send_json(event["payload"])

 @database_sync_to_async
 def can_subscribe(self,user,participant_id,quiz_id):
  if user and user.is_authenticated and user.is_staff: return Quiz.objects.filter(pk=quiz_id).exists()
  return bool(participant_id and Participant.objects.filter(pk=participant_id,is_active=True).exists() and Quiz.objects.filter(pk=quiz_id).exists())
