from unittest.mock import patch
from django.urls import reverse
from rest_framework.test import APITestCase
from users.models import User


class PlayAITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="s3cret")
        self.client.force_authenticate(user=self.user)

    @patch("game.views.get_ai_decision")
    def test_ai_play_correct(self, mock_ai):
        mock_ai.return_value = {
            "result": "correct",
            "message": "paper beats rock",
            "explanation": "paper covers rock"
        }
        url = reverse("play")
        response = self.client.post(url, {"move": "paper"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["result"], "correct")
        self.assertIn("session_id", response.data)

    @patch("game.views.get_ai_decision")
    def test_ai_play_lost(self, mock_ai):
        mock_ai.return_value = {
            "result": "lost",
            "message": "paper does not beat scissors",
            "explanation": "scissors cut paper"
        }
        url = reverse("play")
        response = self.client.post(url, {"move": "paper"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["result"], "lost")
