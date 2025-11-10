from django.contrib import admin
from .models import GameSession, Score


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "active", "created_at", "updated_at", "ended_at"]
    list_filter = ["active", "created_at"]
    search_fields = ["user__username", "id"]
    readonly_fields = ["id", "created_at", "updated_at", "ended_at"]
    ordering = ["-created_at"]


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "session", "points", "recorded_at"]
    list_filter = ["recorded_at"]
    search_fields = ["user__username", "session__id"]
    readonly_fields = ["id", "recorded_at"]
    ordering = ["-recorded_at"]
