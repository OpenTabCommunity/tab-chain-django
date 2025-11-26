from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import SignupSerializer, UserProfileSerializer, UserHistorySerializer
from .models import User


class SignupView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = SignupSerializer
    permission_classes = [AllowAny]


class LoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = SignupSerializer

    def post(self, request):
        username = request.data.get('username')
        user = User.objects.filter(username=username).first()
        if not user: 
            return Response({'detail': 'invalid credentials'}, status=401)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'expires_in': 3600
        })



class UserMeView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user


class UserHistoryView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserHistorySerializer
    lookup_field = 'id'
    queryset = User.objects.all()
