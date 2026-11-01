"""Role based access control decorators."""

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def _reject(request, message="You do not have access to that page."):
    messages.error(request, message)
    return redirect("core:home")


def role_required(*roles):
    """Allow only the listed roles. Superusers always pass."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect("accounts:login")
            if user.is_superuser or user.is_platform_admin:
                return view(request, *args, **kwargs)
            if user.role not in roles:
                return _reject(request)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def admin_required(view):
    """Staff-only views (console, verification, check-in)."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return redirect("accounts:login")
        if not (user.is_platform_admin or user.is_staff or user.is_superuser):
            return _reject(request, "That area is limited to LifeLink administrators.")
        return view(request, *args, **kwargs)

    return wrapper


def donor_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.donor_profile:
            messages.info(
                request,
                "Complete a donor profile to use donor features.",
            )
            return redirect("accounts:profile")
        return view(request, *args, **kwargs)

    return wrapper
