from django.test import TestCase
from rest_framework.test import APIClient
from users.models import User
from game.models import GameSession, Score
from django.utils import timezone
from unittest.mock import patch


class GameFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.username = "bob"
        self.password = "pass123"
        User.objects.create_user(username=self.username, password=self.password)

        res = self.client.post("/api/auth/login", {
            "username": self.username,
            "password": self.password
        }, format="json")
        self.assertEqual(res.status_code, 200)
        token = res.data["access_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        GameSession.objects.all().delete()
        Score.objects.all().delete()

    @patch("game.views.get_ai_decision")
    def test_play_win_and_end_session(self, mock_ai):
        mock_ai.return_value = {
            "result": "correct",
            "message": "rock beats scissors",
            "explanation": "rock smashes scissors"
        }

        res = self.client.post("/api/play", {"move": "rock"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"], "correct")
        self.assertIn("session_id", res.data)

        session_id = res.data["session_id"]
        res2 = self.client.post(f"/api/session/{session_id}/end", {"reason": "quit"}, format="json")
        self.assertEqual(res2.status_code, 200)
        self.assertIn("final_score", res2.data)

    @patch("game.views.get_ai_decision")
    def test_play_tie(self, mock_ai):
        mock_ai.return_value = {
            "result": "tie",
            "message": "rock equals rock",
            "explanation": "same move"
        }

        res = self.client.post("/api/play", {"move": "rock"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertIn(res.data["result"], ["tie", "lost", "correct"])
        self.assertIn("session_id", res.data)

    @patch("game.views.get_ai_decision")
    def test_play_lose(self, mock_ai):
        mock_ai.return_value = {
            "result": "lost",
            "message": "paper beats rock",
            "explanation": "paper covers rock"
        }

        res = self.client.post("/api/play", {"move": "rock"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"], "lost")
        self.assertIn("final_score", res.data)

    @patch("game.views.get_ai_decision")
    def test_ai_service_unavailable(self, mock_ai):
        mock_ai.return_value = {"result": "error", "message": "AI down"}

        res = self.client.post("/api/play", {"move": "rock"}, format="json")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.data["error"], "AI service unavailable")

    def test_invalid_move_rejected(self):
        res = self.client.post("/api/play", {"move": "banana"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"], "invalid move")

    def test_end_nonexistent_session(self):
        res = self.client.post("/api/session/00000000-0000-0000-0000-000000000000/end", {}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_leaderboard_and_history(self):
        user = User.objects.get(username=self.username)
        session = GameSession.objects.create(user=user, active=False, chain=["rock", "paper"])
        Score.objects.create(user=user, session=session, points=5)

        res = self.client.get("/api/leaderboard/top?limit=5")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(len(res.data) >= 1)
        self.assertIn("username", res.data[0])
        self.assertIn("best_score", res.data[0])
