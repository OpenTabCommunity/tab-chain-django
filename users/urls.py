from django.urls import path
from .views import SignupView, LoginView, UserMeView, UserHistoryView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('signup', SignupView.as_view()),
    path('login', LoginView.as_view()),
    path('refresh', TokenRefreshView.as_view()),
    path('me', UserMeView.as_view()),
    path('<int:id>/history', UserHistoryView.as_view()),
]
