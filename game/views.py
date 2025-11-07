from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Max
from django.db import transaction
from users.models import User
from .models import GameSession, Score
from .serializers import GameSessionSerializer
import random

MOVES = ["rock", "paper", "scissors"]
WINNING = {
    "rock": "scissors",
    "paper": "rock",
    "scissors": "paper",
}


def beats(a, b):
    return WINNING.get(a) == b


class PlayView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        move = request.data.get("move")
        session_id = request.data.get("session_id")

        if move not in MOVES:
            return Response({"error": "invalid move"}, status=status.HTTP_400_BAD_REQUEST)

        if session_id:
            try:
                session = GameSession.objects.get(id=session_id, user=request.user)
            except GameSession.DoesNotExist:
                return Response({"error": "session not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
            session = GameSession.objects.filter(user=request.user, active=True).first()
            if not session:
                session = GameSession.objects.create(user=request.user)

        ai_move = random.choice(MOVES)
        chain = session.chain + [move]
        session.chain = chain
        session.updated_at = timezone.now()

        if beats(move, ai_move):
            session.save()
            with transaction.atomic():
                score, created = Score.objects.get_or_create(
                    user=request.user, session=session, defaults={"points": 0}
                )
                score.points += 1
                score.save()

            return Response({
                "result": "correct",
                "session_id": str(session.id),
                "chain": chain,
                "message": f"{move} beats {ai_move}",
                "explanation": f"{move} covers {ai_move}" if move == "paper" else f"{move} beats {ai_move}",
                "current_score": score.points,
            }, status=status.HTTP_200_OK)

        if ai_move == move:
            session.save()
            return Response({
                "result": "tie",
                "session_id": str(session.id),
                "chain": chain,
                "message": f"Both played {move}",
                "explanation": "It's a tie, play again!"
            }, status=status.HTTP_200_OK)

        session.active = False
        session.ended_at = timezone.now()
        session.save()

        final_score = Score.objects.filter(user=request.user, session=session).first()
        final_points = final_score.points if final_score else 0

        return Response({
            "result": "lost",
            "session_id": str(session.id),
            "final_score": final_points,
            "message": f"{move} does not beat {ai_move}",
            "explanation": f"{ai_move} beats {move}",
        }, status=status.HTTP_200_OK)


class SessionDetailView(generics.RetrieveAPIView):

    queryset = GameSession.objects.all()
    serializer_class = GameSessionSerializer
    permission_classes = [IsAuthenticated]


class EndSessionView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            session = GameSession.objects.get(id=pk, user=request.user)
        except GameSession.DoesNotExist:
            return Response({"error": "session not found"}, status=status.HTTP_404_NOT_FOUND)

        if not session.active:
            return Response({
                "message": "Session already ended",
                "final_score": Score.objects.filter(user=request.user, session=session)
                                            .aggregate(Max("points"))["points__max"] or 0
            }, status=status.HTTP_200_OK)

        session.active = False
        session.ended_at = timezone.now()
        session.save()

        final_score = Score.objects.filter(user=request.user, session=session).aggregate(Max("points"))["points__max"] or 0

        return Response({
            "message": "Session ended successfully",
            "final_score": final_score
        }, status=status.HTTP_200_OK)


class LeaderboardTopView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = int(request.query_params.get("limit", 10))
        users = (
            User.objects.annotate(best_score=Max("score__points"))
            .filter(best_score__isnull=False)
            .order_by("-best_score")[:limit]
        )
        data = [
            {
                "rank": i + 1,
                "username": u.username,
                "best_score": u.best_score or 0
            }
            for i, u in enumerate(users)
        ]
        return Response(data, status=status.HTTP_200_OK)
