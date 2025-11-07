from django.urls import path
from .views import PlayView, SessionDetailView, EndSessionView

urlpatterns = [
    path('play', PlayView.as_view()),
    path('session/<uuid:pk>', SessionDetailView.as_view()),
    path('session/<uuid:pk>/end', EndSessionView.as_view()),
]
