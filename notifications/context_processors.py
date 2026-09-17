"""Unread notification count for the navbar badge."""


def notification_context(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from .models import Notification

        unread = Notification.objects.filter(recipient=user, is_read=False, is_deleted=False).count()
    else:
        unread = 0
    return {"unread_notifications": unread}
