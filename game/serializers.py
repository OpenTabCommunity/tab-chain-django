from rest_framework import serializers
from .models import GameSession, Score


class GameSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameSession
        fields = ("id", "user", "chain", "active", "created_at", "updated_at", "ended_at")


class ScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Score
        fields = ("user", "session", "points", "recorded_at")
