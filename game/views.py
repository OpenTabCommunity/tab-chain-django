from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Max
from django.db import transaction
import asyncio

from users.models import User
from .models import GameSession, Score
from .serializers import GameSessionSerializer
from .ai_client import get_ai_decision


class PlayView(generics.GenericAPIView):
    """
    Handles a single play action by the user.
    Sends the user's move to the AI service asynchronously
    and records the result in the current session.
    """
    permission_classes = [IsAuthenticated]

    async def _call_ai(self, move: str):
        try:
            result = await get_ai_decision(move)
            if not isinstance(result, dict):
                return {"result": "error", "message": "Invalid AI response"}
            return result
        except Exception as e:
            return {"result": "error", "message": str(e)}

    def post(self, request):
        move = request.data.get("move")
        if not move:
            return Response({"error": "missing move"}, status=400)

        # validate move type
        valid_moves = ["rock", "paper", "scissors"]
        if move not in valid_moves:
            return Response({"error": "invalid move"}, status=400)

        session_id = request.data.get("session_id")
        if session_id:
            try:
                session = GameSession.objects.get(id=session_id, user=request.user)
            except GameSession.DoesNotExist:
                return Response({"error": "session not found"}, status=404)
        else:
            session = GameSession.objects.create(user=request.user)

        ai_response = asyncio.run(self._call_ai(move))
        result = ai_response.get("result")
        message = ai_response.get("message")
        explanation = ai_response.get("explanation")

        if result == "error":
            return Response({"error": "AI service unavailable"}, status=503)

        chain = session.chain + [move]
        session.chain = chain
        session.updated_at = timezone.now()

        if result == "correct":
            current_score = len(chain)
            with transaction.atomic():
                session.save()
                Score.objects.create(user=request.user, session=session, points=current_score)

            return Response({
                "result": "correct",
                "session_id": str(session.id),
                "chain": chain,
                "message": message,
                "explanation": explanation,
                "current_score": current_score
            })

        if result == "tie":
            session.save()
            return Response({
                "result": "tie",
                "session_id": str(session.id),
                "chain": chain,
                "message": message,
                "explanation": explanation
            })

        if result == "lost":
            session.active = False
            session.ended_at = timezone.now()
            with transaction.atomic():
                session.save()
                final_score = len(chain) - 1
                Score.objects.create(user=request.user, session=session, points=final_score)

            return Response({
                "result": "lost",
                "final_score": final_score,
                "message": message,
                "explanation": explanation,
            })

        return Response({"error": "unexpected AI result"}, status=500)


class SessionDetailView(generics.RetrieveAPIView):
    """
    Retrieve a specific game session by ID.
    """
    queryset = GameSession.objects.all()
    serializer_class = GameSessionSerializer
    permission_classes = [IsAuthenticated]


class EndSessionView(generics.GenericAPIView):
    """
    Manually end a game session and return the user's final score.
    """
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

        final_score = Score.objects.filter(user=request.user, session=session).aggregate(Max("points"))[
                          "points__max"] or 0

        return Response({
            "message": "Session ended successfully",
            "final_score": final_score
        }, status=status.HTTP_200_OK)


class LeaderboardTopView(generics.ListAPIView):
    """
    Returns top N players with their best scores.
    """
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
