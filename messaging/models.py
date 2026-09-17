"""Internal messaging: conversations, participants, messages."""
from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    """A thread between two or more participants."""

    subject = models.CharField(max_length=160, blank=True)
    enquiry = models.ForeignKey(
        "marketplace.Enquiry", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="conversations",
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ConversationParticipant",
        related_name="conversations",
    )
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self):
        names = ", ".join(p.user.full_name for p in self.conversation_participants.all()[:3])
        return f"Conversation #{self.pk} ({names})"

    def is_participant(self, user):
        return self.conversation_participants.filter(user=user).exists()


class ConversationParticipant(TimeStampedModel):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="conversation_participants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversation_participants"
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"], name="unique_conversation_participant"
            )
        ]

    def __str__(self):
        return f"{self.user} in {self.conversation_id}"


class Message(TimeStampedModel):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    body = models.TextField(max_length=4000)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"Msg #{self.pk} by {self.sender}"
