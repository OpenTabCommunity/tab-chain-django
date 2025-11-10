from django.urls import path
from .views import PlayView, SessionDetailView, EndSessionView, LeaderboardTopView

urlpatterns = [
    path("play", PlayView.as_view(), name="play"),
    path('session/<uuid:pk>', SessionDetailView.as_view()),
    path('session/<uuid:pk>/end', EndSessionView.as_view()),
    path('leaderboard/top', LeaderboardTopView.as_view()),
]
