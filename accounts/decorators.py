"""Server-side role-based access control decorators."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Require the authenticated user to have one of the given roles.

    Usage::

        @role_required("STUDENT", "PARENT")
        def view(request): ...
    """

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.is_platform_admin and "ADMIN" in roles:
                return view_func(request, *args, **kwargs)
            if user.role not in roles:
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


admin_required = role_required("ADMIN")
student_required = role_required("STUDENT")
parent_required = role_required("PARENT")
tutor_required = role_required("TUTOR")
student_or_parent_required = role_required("STUDENT", "PARENT")
