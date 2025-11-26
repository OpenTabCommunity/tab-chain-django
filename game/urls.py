from django.urls import path
from .views import MoveAPIView, EndSessionAPIView, LeaderboardTopView, CurrentSessionAPIView

urlpatterns = [
    path("play", MoveAPIView.as_view(), name="play"),
    path('session/<uuid:session_id>/end', EndSessionAPIView.as_view()),
    path('leaderboard/top', LeaderboardTopView.as_view()),
    path('session/current/', CurrentSessionAPIView.as_view(), name='current-session'),
]
