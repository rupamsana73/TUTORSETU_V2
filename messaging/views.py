"""Messaging views. Access strictly limited to conversation participants."""
from django.contrib import messages as dj_messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from core.ratelimits import RATE_LIMITS
from notifications.models import NotificationType
from notifications.services import notify

from .models import Conversation, ConversationParticipant, Message


@login_required
def conversation_list(request):
    conversations = (
        Conversation.objects.filter(participants=request.user)
        .prefetch_related("conversation_participants__user", "messages")
    )
    search = request.GET.get("q", "").strip()
    if search:
        conversations = conversations.filter(
            Q(subject__icontains=search)
            | Q(conversation_participants__user__full_name__icontains=search)
        ).distinct()
    items = []
    for conv in conversations[:50]:
        others = [p.user for p in conv.conversation_participants.all() if p.user_id != request.user.pk]
        participant = conv.conversation_participants.filter(user=request.user).first()
        last_message = conv.messages.last()
        unread = 0
        if participant and participant.last_read_at:
            unread = conv.messages.filter(
                created_at__gt=participant.last_read_at
            ).exclude(sender=request.user).count()
        elif participant:
            unread = conv.messages.exclude(sender=request.user).count()
        items.append(
            {"conversation": conv, "others": others, "last_message": last_message, "unread": unread}
        )
    return render(request, "messaging/conversation_list.html", {"items": items, "search": search})


@login_required
def conversation_detail(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.prefetch_related("conversation_participants__user"),
        pk=conversation_id,
    )
    if not conversation.is_participant(request.user):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("You are not a participant in this conversation.")
    msgs = conversation.messages.select_related("sender")[:200]
    ConversationParticipant.objects.filter(
        conversation=conversation, user=request.user
    ).update(last_read_at=timezone.now())
    others = [p.user for p in conversation.conversation_participants.all() if p.user_id != request.user.pk]
    return render(
        request,
        "messaging/conversation_detail.html",
        {"conversation": conversation, "messages_list": msgs, "others": others},
    )


@ratelimit(key="user", rate=RATE_LIMITS["message"], method="POST", block=True)
@require_POST
@login_required
def send_message(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    if not conversation.is_participant(request.user):
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("You are not a participant in this conversation.")
    body = (request.POST.get("body") or "").strip()
    if not body:
        dj_messages.error(request, "Message cannot be empty.")
        return redirect("messaging:conversation", conversation_id=conversation_id)
    with transaction.atomic():
        message = Message.objects.create(
            conversation=conversation, sender=request.user, body=body[:4000]
        )
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=["last_message_at"])
    recipients = conversation.participants.exclude(pk=request.user.pk)
    for recipient in recipients:
        notify(
            recipient, NotificationType.NEW_MESSAGE,
            f"New message from {request.user.full_name}",
            body[:200],
            url=f"/messages/{conversation.pk}/",
        )
    return redirect("messaging:conversation", conversation_id=conversation_id)


@ratelimit(key="user", rate=RATE_LIMITS["message"], method="POST", block=True)
@require_POST
@login_required
def start_conversation(request, user_id):
    """Start a direct conversation with another user (by user id)."""
    from django.contrib.auth import get_user_model

    other = get_object_or_404(get_user_model(), pk=user_id)
    if other == request.user:
        dj_messages.error(request, "You cannot message yourself.")
        return redirect("messaging:list")
    from .services import get_or_create_conversation

    conversation = get_or_create_conversation([request.user, other])
    return redirect("messaging:conversation", conversation_id=conversation.pk)
