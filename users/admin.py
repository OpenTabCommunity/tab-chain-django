from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ["id", "username", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["username"]
    readonly_fields = ["id", "created_at"]
    ordering = ["-created_at"]
