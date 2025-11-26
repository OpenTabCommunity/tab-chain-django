import uuid
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


class MoveSerializer(serializers.Serializer):
    move = serializers.CharField(max_length=64)
    chain = serializers.ListField(child=serializers.CharField(max_length=64), required=False)
    session_id = serializers.UUIDField(required=False, allow_null=True)

class EndSessionResponseSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    final_score = serializers.IntegerField()
    best_score = serializers.IntegerField()
    message = serializers.CharField()

