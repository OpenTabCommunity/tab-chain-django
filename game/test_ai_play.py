from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from users.models import User
from game.models import GameSession, Score


class PlayAITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="s3cret")
        self.client.force_authenticate(user=self.user)
        self.url = reverse("play")

    @patch("game.views.get_ai_decision")
    def test_ai_play_correct(self, mock_ai):
        """ Should win when AI returns 'correct'"""
        mock_ai.return_value = {
            "result": "correct",
            "message": "paper beats rock",
            "explanation": "paper covers rock",
        }

        response = self.client.post(self.url, {"move": "paper"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "correct")
        self.assertIn("session_id", response.data)
        self.assertIn("message", response.data)
        self.assertIn("explanation", response.data)
        self.assertIn("current_score", response.data)

        # Database consistency check
        session = GameSession.objects.get(id=response.data["session_id"])
        self.assertTrue(session.active)
        self.assertEqual(Score.objects.filter(user=self.user).count(), 1)

    @patch("game.views.get_ai_decision")
    def test_ai_play_lost(self, mock_ai):
        """ Should lose when AI returns 'lost'"""
        mock_ai.return_value = {
            "result": "lost",
            "message": "paper does not beat scissors",
            "explanation": "scissors cut paper",
        }

        response = self.client.post(self.url, {"move": "paper"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["result"], "lost")
        self.assertIn("message", response.data)
        self.assertIn("explanation", response.data)
        self.assertIn("final_score", response.data)

        # Verify session deactivated
        session = GameSession.objects.order_by("-created_at").first()
        self.assertFalse(session.active)
        self.assertIsNotNone(session.ended_at)

    @patch("game.views.get_ai_decision")
    def test_ai_service_error(self, mock_ai):
        """ Should handle AI service failure gracefully"""
        mock_ai.return_value = {"result": "error", "message": "AI service unavailable"}

        response = self.client.post(self.url, {"move": "rock"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["error"], "AI service unavailable")

    def test_invalid_move_rejected(self):
        """ Should reject invalid player move"""
        response = self.client.post(self.url, {"move": "banana"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "invalid move")

    def test_missing_move_field(self):
        """ Should reject missing 'move' key in request"""
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "missing move")
