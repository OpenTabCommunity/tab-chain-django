from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Max
from django.db import transaction
from asgiref.sync import async_to_sync

from users.models import User
from .models import GameSession, Score
from .serializers import GameSessionSerializer
from .ai_client import get_ai_decision

import logging

logger = logging.getLogger(__name__)

# Constants
MOVES = ("rock", "paper", "scissors")


# Utils

def safe_int(value, default=10, cap=100):
    """Safe conversion for leaderboard limit"""
    try:
        val = int(value)
        return min(max(val, 1), cap)
    except (TypeError, ValueError):
        return default


# Views

class PlayView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        move = request.data.get("move")

        # Input validation
        if not move:
            return Response({"error": "missing move"}, status=status.HTTP_400_BAD_REQUEST)

        if move not in MOVES:
            return Response({"error": "invalid move"}, status=status.HTTP_400_BAD_REQUEST)

        session_id = request.data.get("session_id")
        session = None
        # Ensure thread-safety using select_for_update inside a transaction
        with transaction.atomic():
            if session_id:
                try:
                    session = (
                        GameSession.objects.select_for_update()
                        .get(id=session_id, user=request.user)
                    )
                except GameSession.DoesNotExist:
                    return Response(
                        {"error": "session not found"},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                session = GameSession.objects.create(user=request.user)

            # Ensure chain is always a list
            if not isinstance(session.chain, list):
                session.chain = []

            # Call external AI service (non-blocking)
            ai_response = async_to_sync(get_ai_decision)(move)

            # Defensive validation of AI response
            if not isinstance(ai_response, dict) or "result" not in ai_response:
                logger.warning(f"Bad AI response: {ai_response}")
                return Response(
                    {"error": "Invalid AI response"},
                    status=status.HTTP_502_BAD_GATEWAY
                )

            result = ai_response.get("result")
            message = ai_response.get("message", "")
            explanation = ai_response.get("explanation", "")

            if result == "error":
                return Response(
                    {"error": "AI service unavailable"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # Append move to chain
            session.chain.append(move)
            session.updated_at = timezone.now()

            # Scoring logic
            # If player wins -> +1 score; if loses -> session ends and save score-1
            if result == "correct":
                current_score = len(session.chain)
                session.save()
                Score.objects.create(
                    user=request.user, session=session, points=current_score
                )
                return Response(
                    {
                        "result": "correct",
                        "session_id": str(session.id),
                        "chain": session.chain,
                        "message": message,
                        "explanation": explanation,
                        "current_score": current_score,
                    },
                    status=status.HTTP_200_OK,
                )

            # Lose case: finalize session
            session.active = False
            session.ended_at = timezone.now()
            session.save()

            final_score = max(len(session.chain) - 1, 0)
            Score.objects.create(
                user=request.user, session=session, points=final_score
            )

            return Response(
                {
                    "result": "lost",
                    "session_id": str(session.id),
                    "final_score": final_score,
                    "message": message,
                    "explanation": explanation,
                },
                status=status.HTTP_200_OK,
            )


# Session Detail View
class SessionDetailView(generics.RetrieveAPIView):
    queryset = GameSession.objects.all()
    serializer_class = GameSessionSerializer
    permission_classes = [IsAuthenticated]


# End Session View

class EndSessionView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            session = GameSession.objects.get(id=pk, user=request.user)
        except GameSession.DoesNotExist:
            return Response(
                {"error": "session not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not session.active:
            final_score = (
                    Score.objects.filter(user=request.user, session=session)
                    .aggregate(Max("points"))["points__max"] or 0
            )
            return Response(
                {
                    "message": "Session already ended",
                    "final_score": final_score,
                },
                status=status.HTTP_200_OK,
            )

        with transaction.atomic():
            session.active = False
            session.ended_at = timezone.now()
            session.save()

            final_score = (
                    Score.objects.filter(user=request.user, session=session)
                    .aggregate(Max("points"))["points__max"] or 0
            )

        return Response(
            {
                "message": "Session ended successfully",
                "final_score": final_score,
            },
            status=status.HTTP_200_OK,
        )


# Leaderboard View
class LeaderboardTopView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = safe_int(request.query_params.get("limit"), default=10, cap=100)
        users = (
            User.objects.annotate(best_score=Max("score__points"))
            .filter(best_score__isnull=False)
            .order_by("-best_score")[:limit]
        )

        data = [
            {
                "rank": i + 1,
                "username": u.username,
                "best_score": u.best_score or 0,
            }
            for i, u in enumerate(users)
        ]

        return Response(data, status=status.HTTP_200_OK)
