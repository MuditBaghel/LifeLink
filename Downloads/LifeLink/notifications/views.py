"""Notification centre and notification preferences."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import Notification
from .services import get_preferences


@login_required
def notification_list(request):
    queryset = request.user.notifications.all()
    scope = request.GET.get("scope", "all")
    kind = request.GET.get("kind", "")

    if scope == "unread":
        queryset = queryset.filter(is_read=False)
    if kind:
        queryset = queryset.filter(kind=kind)

    paginator = Paginator(queryset, 15)
    page = paginator.get_page(request.GET.get("page"))
    unread_total = request.user.notifications.filter(is_read=False).count()

    return render(
        request,
        "notifications/list.html",
        {
            "page": page,
            "unread_total": unread_total,
            "total": paginator.count,
            "scope": scope,
            "kind": kind,
            "kinds": Notification.Kind.choices,
        },
    )


@login_required
def mark_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method == "POST":
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        if notification.url:
            return HttpResponseRedirect(notification.url)
    return redirect("notifications:list")


@login_required
def open_notification(request, pk):
    """Follow a notification and mark it read in one step."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect(notification.url or "notifications:list")


@login_required
def mark_all_read(request):
    if request.method == "POST":
        updated = request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, f"{updated} notification(s) marked as read.")
    return redirect(reverse("notifications:list"))


@login_required
def preferences(request):
    prefs = get_preferences(request.user)
    if request.method == "POST":
        prefs.matching_requests = "matching_requests" in request.POST
        prefs.emergency_requests = "emergency_requests" in request.POST
        prefs.donor_responses = "donor_responses" in request.POST
        prefs.request_updates = "request_updates" in request.POST
        prefs.camp_updates = "camp_updates" in request.POST
        prefs.donation_updates = "donation_updates" in request.POST
        prefs.save()
        messages.success(request, "Notification preferences saved.")
        return redirect("notifications:preferences")
    return render(request, "notifications/preferences.html", {"prefs": prefs})
