"""Messaging access-control tests."""
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User, UserRole

from .models import Conversation, Message
from .services import get_or_create_conversation


@override_settings(RATELIMIT_ENABLE=False)
class MessagingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(
            email="alice@example.com", password="Passw0rd!23", role=UserRole.STUDENT)
        cls.bob = User.objects.create_user(
            email="bob@example.com", password="Passw0rd!23", role=UserRole.TUTOR)
        cls.eve = User.objects.create_user(
            email="eve@example.com", password="Passw0rd!23", role=UserRole.STUDENT)

    def test_conversation_reuse(self):
        c1 = get_or_create_conversation([self.alice, self.bob])
        c2 = get_or_create_conversation([self.bob, self.alice])
        self.assertEqual(c1.pk, c2.pk)

    def test_send_and_read_message(self):
        conv = get_or_create_conversation([self.alice, self.bob])
        self.client.force_login(self.alice)
        response = self.client.post(reverse("messaging:send", args=[conv.pk]),
                                    {"body": "Hello tutor!"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Message.objects.filter(conversation=conv, body="Hello tutor!").exists())
        conv.refresh_from_db()
        self.assertIsNotNone(conv.last_message_at)

    def test_non_participant_forbidden(self):
        conv = get_or_create_conversation([self.alice, self.bob])
        self.client.force_login(self.eve)
        response = self.client.get(reverse("messaging:conversation", args=[conv.pk]))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(reverse("messaging:send", args=[conv.pk]),
                                    {"body": "sneaky"})
        self.assertEqual(response.status_code, 403)

    def test_start_conversation_with_self_blocked(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("messaging:start", args=[self.alice.pk]),
                                    follow=True)
        self.assertFalse(Conversation.objects.filter(
            conversation_participants__user=self.alice
        ).exclude(pk__in=[]).filter(subject="").exists())
        self.assertFalse(Conversation.objects.filter(
            conversation_participants__user=self.alice).count() > 0)
