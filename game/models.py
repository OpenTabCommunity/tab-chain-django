import uuid
from django.db import models
from django.utils import timezone
from django.db import transaction
from django.db.models import Count

from users.models import User


class GameSession(models.Model):
    """
    GameSession: one session per game. The 'chain' is stored in ChainEntry rows.
    Use end_session() to finish a session and record a Score reliably.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="game_sessions")
    active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        status = "active" if self.active else "ended"
        return f"Session {self.id} ({status})"

    def chain_length(self):
        """
        Return number of ChainEntry rows linked to this session.
        Use this as the canonical 'points' calculation.
        """
        return self.chain_entries.count()

    @property
    def points(self):
        """
        Convenience property: points are equal to chain length.
        """
        return self.chain_length()

    def add_chain_item(self, value: str):
        """
        Add a new chain item at the end. Use this instead of creating ChainEntry manually
        to ensure proper ordering.
        """
        last_position = self.chain_entries.aggregate(max_pos=models.Max("position"))["max_pos"] or 0
        return ChainEntry.objects.create(session=self, position=last_position + 1, value=value)

    def end_session(self, record_score: bool = True):
        """
        Mark session ended, compute points (chain length), and optionally record a Score atomically.
        Returns the Score instance if recorded, else None.
        """
        if not self.active:
            # already ended
            return None

        with transaction.atomic():
            # Make sure no other process is racing to write entries
            self.active = False
            self.ended_at = timezone.now()
            self.save(update_fields=["active", "ended_at", "updated_at"])

            if record_score:
                points = self.chain_length()
                score = Score.objects.create(user=self.user, session=self, points=points)
                return score
            return None


class ChainEntry(models.Model):
    """
    One element of the chain. Normalized storage makes it easy to query lengths,
    search values, and index positions. Values are limited in length (tune max_length to your domain).
    """
    session = models.ForeignKey(GameSession, on_delete=models.CASCADE, related_name="chain_entries")
    position = models.PositiveIntegerField(help_text="1-based index of the chain item within the session")
    value = models.CharField(max_length=64, help_text="chain step, e.g. 'rock', 'paper', 'scissors'")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("session", "position"),)
        ordering = ["session", "position"]
        indexes = [
            models.Index(fields=["session", "position"]),
            models.Index(fields=["value"]),
        ]

    def __str__(self):
        return f"{self.session_id}#{self.position}: {self.value}"


class Score(models.Model):
    """
    Record of a user's points for a session. Points are intentionally stored as a snapshot
    (derived from chain length at session end) so leaderboards remain correct even if
    chain entries change later (though they shouldn't).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="scores")
    session = models.ForeignKey(GameSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="scores")
    points = models.PositiveIntegerField(db_index=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["-points"]),
            models.Index(fields=["user"]),
            models.Index(fields=["recorded_at"]),
        ]
        ordering = ["-points", "recorded_at"]

    def __str__(self):
        return f"{self.user} — {self.points} pts ({self.recorded_at:%Y-%m-%d %H:%M})"

