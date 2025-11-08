from rest_framework.test import APITestCase


class AuthTests(APITestCase):
    def setUp(self):
        self.signup_url = '/api/auth/signup'
        self.login_url = '/api/auth/login'

    def test_signup_and_login(self):
        res = self.client.post(self.signup_url, {'username': 'alice', 'password': 's3cret'})
        self.assertEqual(res.status_code, 201)
        res = self.client.post(self.login_url, {'username': 'alice', 'password': 's3cret'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('access_token', res.data)
