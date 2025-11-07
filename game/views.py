from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import GameSession, Score
from .serializers import GameSessionSerializer

MOVES = ["rock", "paper", "scissors"]


def beats(a, b):
    return (a == "rock" and b == "scissors") or (a == "paper" and b == "rock") or (a == "scissors" and b == "paper")


class PlayView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        move = request.data.get('move')
        if move not in MOVES:
            return Response({'error': 'invalid move'}, status=400)

        session_id = request.data.get('session_id')
        session = None
        if session_id:
            try:
                session = GameSession.objects.get(id=session_id, user=request.user)
            except GameSession.DoesNotExist:
                return Response({'error': 'session not found'}, status=404)
        else:
            session = GameSession.objects.create(user=request.user)

        import random
        ai_move = random.choice(MOVES)
        chain = session.chain + [move]
        session.chain = chain
        session.updated_at = timezone.now()

        if beats(move, ai_move):
            current_score = len(chain)
            session.save()
            Score.objects.create(user=request.user, session=session, points=current_score)
            return Response({
                "result": "correct",
                "session_id": str(session.id),
                "chain": chain,
                "message": f"{move} beats {ai_move}",
                "explanation": f"{move} beats {ai_move}",
                "current_score": current_score
            })

        session.active = False
        session.ended_at = timezone.now()
        session.save()
        final_score = len(chain) - 1
        Score.objects.create(user=request.user, session=session, points=final_score)
        return Response({
            "result": "lost",
            "final_score": final_score,
            "message": f"{move} does not beat {ai_move}",
            "explanation": f"{ai_move} beats {move}",
        })


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
            return Response(status=404)
        session.active = False
        session.ended_at = timezone.now()
        session.save()
        final_score = len(session.chain)
        return Response({'final_score': final_score})
