"""Conversation helpers."""
from django.db import transaction

from .models import Conversation, ConversationParticipant


def get_or_create_conversation(users, subject="", enquiry=None):
    """Find an existing 1:1 conversation or create a new one (atomic)."""
    user_ids = sorted(u.pk for u in users)
    if len(user_ids) == 2:
        existing = (
            Conversation.objects.filter(conversation_participants__user_id=user_ids[0])
            .filter(conversation_participants__user_id=user_ids[1])
            .distinct()
        )
        for conv in existing:
            if conv.conversation_participants.count() == 2:
                return conv
    with transaction.atomic():
        conversation = Conversation.objects.create(subject=subject[:160], enquiry=enquiry)
        ConversationParticipant.objects.bulk_create(
            [ConversationParticipant(conversation=conversation, user_id=uid) for uid in user_ids]
        )
    return conversation
