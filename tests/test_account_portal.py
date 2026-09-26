"""Integration tests for staging account routes. Requires fastapi and httpx."""
import os
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class AccountPortalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["FORMOCHKA_ACCOUNT_DB"] = cls.tmp.name + "/test-users.db"
        os.environ["FORMOCHKA_PUBLIC_URL"] = "https://testserver"
        from web import account_portal as p
        cls.p = p
        app = FastAPI()
        app.include_router(p.router)
        cls.client = TestClient(app, base_url="https://testserver")
        cls.sent = []

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.tmp.cleanup()

    def post(self, path, payload):
        return self.client.post(path, json=payload, headers={"Origin": "https://testserver"})

    def test_full_workflow(self):
        async def fake_send(recipient, kind, token):
            self.sent.append((recipient, kind, token))

        with patch.object(self.p, "smtp_settings", return_value={"configured": True}), \
                patch.object(self.p, "send_later", side_effect=fake_send):
            ch = self.client.get("/account/captcha").json()
            with self.p.store.connect() as db:
                answer = db.execute("SELECT answer FROM captcha_challenges WHERE id=?", (ch["id"],)).fetchone()[0]
            r = self.post("/account/signup", {
                "display_name": "Тестовый пользователь", "email": "TestUSER@example.com",
                "password": "StrongStagingPassword2026!", "avatar_emoji": "🍓",
                "captcha_id": ch["id"], "captcha_answer": answer,
                "privacy_accepted": True, "newsletter": False
            })
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(len(self.sent), 1)
            self.assertEqual(self.sent[0][1], "verify")
            self.assertIsNone(self.p.store.authenticate("testuser@example.com", "StrongStagingPassword2026!"))
            self.assertEqual(self.p.store.find_user("testuser@example.com")["email"], "testuser@example.com")
            ch2 = self.client.get("/account/captcha").json()
            with self.p.store.connect() as db:
                answer2 = db.execute("SELECT answer FROM captcha_challenges WHERE id=?", (ch2["id"],)).fetchone()[0]
            self.assertEqual(self.post("/account/signup", {
                "display_name": "Другой", "email": "testuser@example.com",
                "password": "StrongStagingPassword2026!", "avatar_emoji": "🍓",
                "captcha_id": ch2["id"], "captcha_answer": answer2,
                "privacy_accepted": True, "newsletter": True
            }).status_code, 409)
            verify = self.client.get("/account/verify", params={"token": self.sent[0][2]},
                                     follow_redirects=False)
            self.assertEqual(verify.status_code, 303)
            self.assertEqual(verify.headers["location"], "/")
            self.assertIn("__Host-f3d-session", self.client.cookies)
            self.assertEqual(self.client.get("/account/api/me").json()["name"], "Тестовый пользователь")
            self.assertEqual(self.client.get("/account/verify",
                             params={"token": self.sent[0][2]}, follow_redirects=False).status_code, 400)
            self.assertEqual(self.post("/account/login", {
                "email": "testuser@example.com", "password": "StrongStagingPassword2026!"
            }).status_code, 200)
            self.assertIn("__Host-f3d-session", self.client.cookies)
            self.assertEqual(self.client.get("/account/").status_code, 200)
            self.assertEqual(self.post("/account/newsletter", {"subscribed": True}).status_code, 200)
            user = self.p.store.find_user("testuser@example.com")
            with self.p.store.connect() as db:
                consent = db.execute("SELECT consent_at,unsubscribed_at FROM newsletter_subscriptions WHERE user_id=?",
                                     (user["id"],)).fetchone()
            self.assertIsNotNone(consent["consent_at"])
            self.assertIsNone(consent["unsubscribed_at"])
            self.assertEqual(self.post("/account/newsletter", {"subscribed": False}).status_code, 200)
            self.assertEqual(self.client.get("/admin/").status_code, 403)
            self.assertEqual(self.client.get("/admin/users.csv").status_code, 403)
            self.assertEqual(self.post("/account/logout", {}).status_code, 200)

        admin_id = self.p.store.register("owner@example.com", "AdminStrongStagingPassword2026!")
        with self.p.store.connect() as db:
            db.execute("UPDATE users SET role='admin', verified_at=? WHERE id=?", (int(time.time()), admin_id))
        self.assertEqual(self.post("/account/login", {
            "email": "owner@example.com", "password": "AdminStrongStagingPassword2026!"
        }).status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
        r = self.client.get("/admin/api/users")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["stats"]["total"], 2)
        self.assertEqual(r.json()["stats"]["subscribed"], 0)
        self.assertEqual(len(r.json()["users"]), 2)
        csv_response = self.client.get("/admin/users.csv")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("testuser@example.com", csv_response.text)
        self.assertIn("owner@example.com", csv_response.text)
        self.assertEqual(self.post("/admin/api/users/" + str(admin_id) + "/disable", {"disabled": True}).status_code, 404)
        self.assertEqual(self.post("/account/newsletter", {"subscribed": True}).status_code, 200)
        self.assertEqual(self.client.get("/admin/api/users").json()["stats"]["subscribed"], 1)
        self.assertEqual(len(self.client.get("/admin/api/users?filter=newsletter").json()["users"]), 1)
        self.assertEqual(self.post("/admin/api/users/" + str(user["id"]) + "/disable",
                                   {"disabled": True}).status_code, 200)
        self.assertEqual(self.p.store.find_user("testuser@example.com")["disabled_at"] is not None, True)
        self.assertEqual(self.post("/account/logout", {}).status_code, 200)
        self.assertEqual(self.post("/account/login", {
            "email": "testuser@example.com", "password": "StrongStagingPassword2026!"
        }).status_code, 401)
        self.assertEqual(self.post("/admin/api/users/" + str(admin_id) + "/disable",
                                   {"disabled": True}).status_code, 401)
        self.assertEqual(self.client.get("/admin/api/users").status_code, 401)


if __name__ == "__main__":
    unittest.main()
