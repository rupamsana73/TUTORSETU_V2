"""Notification service — single entry point used across the platform."""
import logging

from django.core.mail import send_mail

from .models import Notification, NotificationType

logger = logging.getLogger("tutorsetu")


def notify(recipient, notification_type, title, body="", url="", send_email=False):
    """Create an in-app notification; optionally email the user. Never raises."""
    try:
        notification = Notification.objects.create(
            recipient=recipient,
            notification_type=notification_type,
            title=title[:200],
            body=body,
            url=url,
        )
        if send_email and recipient.email:
            try:
                send_mail(
                    subject=f"TutorSetu: {title}",
                    message=body or title,
                    from_email=None,
                    recipient_list=[recipient.email],
                    fail_silently=True,
                )
                notification.email_sent = True
                notification.save(update_fields=["email_sent"])
            except Exception:  # noqa: BLE001
                logger.exception("Notification email failed for user %s", recipient.pk)
        return notification
    except Exception:  # noqa: BLE001
        logger.exception("Failed to create notification for user %s", recipient.pk)
        return None
