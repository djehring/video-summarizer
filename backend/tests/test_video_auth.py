"""Run from backend: python -m unittest discover -s tests -v."""

import os
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

with patch.dict(os.environ, {"OPENAI_API_KEY": "", "EXA_API_KEY": "", "DATABASE_URL": ""}):
    from app.routers import auth, videos


USER = {"email": "test@example.com", "name": "Test User", "picture": ""}
VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


class VideoAuthenticationTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret", https_only=True)
        app.include_router(auth.router, prefix="/api")
        app.include_router(videos.router, prefix="/api/videos")

        @app.post("/test/session")
        async def create_session(request: Request):
            request.session["user"] = USER
            return USER

        self.client = TestClient(app, base_url="https://testserver")
        self.addCleanup(self.client.close)
        for mapping in (auth.auth_tokens, videos.jobs, videos.job_users):
            self.enterContext(patch.dict(mapping, {}, clear=True))
        self.process_video = self.enterContext(patch.object(videos, "process_video"))
        self.enterContext(patch.object(videos, "is_database_configured", return_value=False))

    def assert_can_submit_and_poll(self, headers=None):
        response = self.client.post(
            "/api/videos/analyze", json={"url": VIDEO_URL}, headers=headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["job_id"]
        self.assertEqual(videos.job_users[job_id], USER["email"])
        self.process_video.assert_called_once_with(job_id, VIDEO_URL)
        response = self.client.get(f"/api/videos/{job_id}", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["job_id"], job_id)

    def test_exchanged_token_can_submit_and_poll_without_cookies(self):
        auth.auth_tokens["one-time-token"] = {"user": USER, "expires": time.time() + 60}
        response = self.client.post(
            "/api/auth/exchange-token", json={"token": "one-time-token"}
        )
        self.assertEqual(response.status_code, 200)
        headers = {"Authorization": f"Bearer {response.json()['token']}"}
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).json(), USER)
        self.assert_can_submit_and_poll(headers)

    def test_session_cookie_can_submit_and_poll(self):
        self.assertEqual(self.client.post("/test/session").status_code, 200)
        self.assert_can_submit_and_poll()

    def test_missing_invalid_and_expired_credentials_are_rejected(self):
        auth.auth_tokens["expired"] = {"user": USER, "expires": time.time() - 1}
        for authorization in (None, "Bearer unknown", "Bearer expired", "Basic invalid"):
            with self.subTest(authorization=authorization):
                headers = {"Authorization": authorization} if authorization else {}
                responses = (
                    self.client.post("/api/videos/analyze", json={"url": VIDEO_URL}, headers=headers),
                    self.client.get("/api/videos/unknown-job", headers=headers),
                )
                for response in responses:
                    self.assertEqual(response.status_code, 401)
                    self.assertEqual(response.json()["detail"], "Not authenticated")
        self.process_video.assert_not_called()
        self.assertEqual(videos.jobs, {})


if __name__ == "__main__":
    unittest.main()
