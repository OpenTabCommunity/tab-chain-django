from django.contrib import admin
from .models import GameSession, Score


class ScoreInline(admin.TabularInline):
    model = Score
    extra = 0
    readonly_fields = ("points", "created_at")


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "active", "created_at", "updated_at", "ended_at", "chain_length")
    list_filter = ("active", "created_at")
    search_fields = ("user__username", "id")
    readonly_fields = ("created_at", "updated_at", "ended_at")
    inlines = [ScoreInline]

    def chain_length(self, obj):
        return len(obj.chain) if obj.chain else 0
    chain_length.short_description = "Moves"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user")


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session", "points", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "session__id")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
