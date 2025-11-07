from rest_framework import serializers
from .models import User
from game.models import Score, GameSession


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'password')

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserProfileSerializer(serializers.ModelSerializer):
    best_score = serializers.SerializerMethodField()
    sessions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'best_score', 'sessions')

    def get_best_score(self, obj):
        score = Score.objects.filter(user=obj).order_by('-points').first()
        return score.points if score else 0

    def get_sessions(self, obj):
        sessions = GameSession.objects.filter(user=obj).order_by('-created_at')[:5]
        return [{'id': str(s.id), 'active': s.active, 'chain': s.chain} for s in sessions]


class UserHistorySerializer(serializers.Serializer):
    scores = serializers.SerializerMethodField()
    sessions = serializers.SerializerMethodField()

    def get_scores(self, obj):
        user = obj
        return [
            {'points': s.points, 'recorded_at': s.recorded_at}
            for s in Score.objects.filter(user=user).order_by('-recorded_at')
        ]

    def get_sessions(self, obj):
        user = obj
        return [
            {'id': str(s.id), 'chain': s.chain, 'active': s.active, 'created_at': s.created_at}
            for s in GameSession.objects.filter(user=user).order_by('-created_at')
        ]
