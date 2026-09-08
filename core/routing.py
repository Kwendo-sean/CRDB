from django.urls import re_path
from .consumers import QuizConsumer
websocket_urlpatterns=[re_path(r"^ws/quizzes/(?P<quiz_id>\d+)/$",QuizConsumer.as_asgi())]
