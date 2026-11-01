"""Notification creation with duplicate protection and preference checks."""

from .models import Notification, NotificationPreference


def get_preferences(user):
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    return prefs


def notify(user, kind, title, body="", url="", dedupe_key="", force=False):
    """Create one notification. Returns the notification or None when suppressed."""
    if user is None:
        return None
    if not force:
        prefs = get_preferences(user)
        if not prefs.allows(kind):
            return None
    if dedupe_key:
        existing = Notification.objects.filter(user=user, dedupe_key=dedupe_key).first()
        if existing:
            return existing
    return Notification.objects.create(
        user=user,
        kind=kind,
        title=title,
        body=body,
        url=url,
        dedupe_key=dedupe_key,
    )


def notify_many(users, kind, title, body="", url="", dedupe_prefix=""):
    """Notify a list of users once each; returns how many notifications were created."""
    created = 0
    seen = set()
    for user in users:
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        key = f"{dedupe_prefix}-{user.pk}" if dedupe_prefix else ""
        if notify(user, kind, title, body, url=url, dedupe_key=key):
            created += 1
    return created
