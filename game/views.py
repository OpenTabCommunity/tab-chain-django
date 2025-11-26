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
from rest_framework.views import APIView
from uuid import UUID

from .models import GameSession, ChainEntry, Score
from .serializers import MoveSerializer, EndSessionResponseSerializer
from .ai_client import get_ai_decision 

import logging
logger = logging.getLogger(__name__)

class MoveAPIView(APIView):
    """
    POST /move
    Body: {"move": "rock", "chain": [...], "session_id": "<uuid>"}
    If session_id is absent/null -> create a new session.
    Returns: {"accepted": True, "quote": "...", "score": <int>, "session_id": "<uuid>", "result": "correct"|"lost"}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        move = serializer.validated_data["move"]
        session_id = serializer.validated_data.get("session_id")

        # Use a transaction and select_for_update on the GameSession row to avoid races
        with transaction.atomic():
            if session_id:
                try:
                    # lock the session row for update so concurrent /move requests for same session serialize
                    session = GameSession.objects.select_for_update().get(id=session_id, user=request.user)
                except (GameSession.DoesNotExist, ValueError, TypeError):
                    return Response({"error": "session not found"}, status=status.HTTP_404_NOT_FOUND)
                if not session.active:
                    return Response({"error": "session already ended"}, status=status.HTTP_400_BAD_REQUEST)
            else:
                session = GameSession.objects.create(user=request.user)
                chain = ChainEntry.objects.create(session=session, position=1, value="rock")

            # compute next position safely while row is locked
            last_pos = ChainEntry.objects.filter(session=session).aggregate(Max("position"))["position__max"] or 0
            next_pos = last_pos + 1

            current_chain_qs = ChainEntry.objects.filter(session=session).order_by("position").values_list("value", flat=True)
            current_chain = list(current_chain_qs)  # e.g. ["rock", "paper", ...]
            logger.info(current_chain)
            try:
                ai_response = async_to_sync(get_ai_decision)(move, chain=current_chain)
            except Exception as e:
                logger.exception("AI decision failed")
                return Response({"error": "AI service error"}, status=status.HTTP_502_BAD_GATEWAY)

            # Defensive validation of AI response
            if not isinstance(ai_response, dict) or "result" not in ai_response:
                logger.warning("Invalid AI response: %r", ai_response)
                return Response({"error": "invalid ai response"}, status=status.HTTP_502_BAD_GATEWAY)

            result = ai_response.get("result")
            message = ai_response.get("message", "")

            # Persist the move to normalized chain table
            ChainEntry.objects.create(session=session, position=next_pos, value=move)

            # update session timestamp
            session.updated_at = timezone.now()
            session.save(update_fields=["updated_at"])

            current_score = ChainEntry.objects.filter(session=session).count()

            if result :
                # Optionally: you can persist intermediate Score snapshots; here we don't create a Score unless session ends.
                return Response(
                    {
                        "accepted": True,
                        "quote": message,
                        "score": current_score,
                        "session_id": str(session.id),
                    },
                    status=status.HTTP_200_OK,
                )

            # If AI says player lost (or any non-'correct' result defined as losing), finalize the session
            # Customize 'lost' detection to match your AI client contract
            session.active = False
            session.ended_at = timezone.now()
            session.save(update_fields=["active", "ended_at", "updated_at"])

            # derive final score (for example: chain length - 1 if last move causes failure, but here we'll use chain length)
            # adjust according to your scoring rules; below uses chain length as canonical points
            final_score = current_score

            # Save a Score snapshot for history/leaderboards
            Score.objects.create(user=request.user, session=session, points=final_score)

            # best score overall for the user (across sessions)
            best_score = Score.objects.filter(user=request.user).aggregate(Max("points"))["points__max"] or 0

            return Response(
                {
                    "accepted": False,
                    "quote": message,
                    "score": final_score,
                    "session_id": str(session.id),
                    "best_score": best_score,
                },
                status=status.HTTP_200_OK,
            )

class EndSessionAPIView(APIView):
    """
    POST /session/<session_id>/end
    Atomically ends the session, writes a Score snapshot (if not already saved), and returns:
    {"session_id": "<uuid>", "final_score": int, "best_score": int, "message": "..."}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        # validate UUID
        try:
            session_uuid = UUID(session_id)
        except Exception:
            return Response({"error": "invalid session id"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                session = GameSession.objects.select_for_update().get(id=session_uuid, user=request.user)
            except GameSession.DoesNotExist:
                return Response({"error": "session not found"}, status=status.HTTP_404_NOT_FOUND)

            # compute final score from chain entries
            final_score = ChainEntry.objects.filter(session=session).count()

            if session.active:
                # mark ended
                session.active = False
                session.ended_at = timezone.now()
                session.save(update_fields=["active", "ended_at", "updated_at"])

                # write Score snapshot once
                Score.objects.create(user=request.user, session=session, points=final_score)

            else:
                # If already ended, try to get the stored snapshot (defensive)
                stored = Score.objects.filter(user=request.user, session=session).aggregate(Max("points"))
                final_score = stored["points__max"] or final_score

            # best score for this user
            best_score = Score.objects.filter(user=request.user).aggregate(Max("points"))["points__max"] or 0

            payload = {
                "session_id": str(session.id),
                "final_score": final_score,
                "best_score": best_score,
                "message": "Session ended" if session.ended_at else "Session already ended",
            }

            response_serializer = EndSessionResponseSerializer(payload)
            return Response(response_serializer.data, status=status.HTTP_200_OK)


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

class CurrentSessionAPIView(APIView):
    """
    GET /session/current/
    Returns the current active session for the authenticated user.
    Returns: {
        "session_id": "<uuid>" or null,
        "chain": ["rock", "paper", ...],
        "score": <int>,
        "best_score": <int>
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get the most recent active session for this user
        try:
            session = GameSession.objects.filter(
                user=request.user,
                active=True
            ).order_by('-created_at').first()
            
            if session:
                # Get the chain for this session
                chain_entries = ChainEntry.objects.filter(
                    session=session
                ).order_by('position').values_list('value', flat=True)
                chain = list(chain_entries)
                
                # Current score is the length of the chain
                current_score = len(chain)
                
                session_id = str(session.id)
            else:
                # No active session
                session_id = None
                chain = ["Rock"]  # Default starting chain
                current_score = 0
            
            # Get best score for the user
            best_score = Score.objects.filter(
                user=request.user
            ).aggregate(Max("points"))["points__max"] or 0
            
            return Response(
                {
                    "session_id": session_id,
                    "chain": chain,
                    "score": current_score,
                    "best_score": best_score,
                },
                status=status.HTTP_200_OK,
            )
            
        except Exception as e:
            logger.exception("Error fetching current session")
            return Response(
                {"error": "Failed to fetch session data"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
