from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(recipient=request.user)[:50]
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
def notification_open(request, notification_id):
    notification = get_object_or_404(
        Notification, pk=notification_id, recipient=request.user
    )
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    target = notification.url if notification.url.startswith("/") else "/notifications/"
    return redirect(target or "/notifications/")


@require_POST
@login_required
def mark_all_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect("notifications:list")
