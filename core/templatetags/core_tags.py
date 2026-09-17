"""Shared template filters."""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Allow dict[key] lookups in templates."""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except AttributeError:
        return None


@register.filter
def star_icons(rating):
    """Render a 5-star string for a numeric rating."""
    try:
        full = int(round(float(rating or 0)))
    except (TypeError, ValueError):
        full = 0
    full = max(0, min(5, full))
    return "★" * full + "☆" * (5 - full)


@register.filter
def attribute(obj, name):
    """Resolve obj.<name> dynamically (used by generic admin tables)."""
    value = getattr(obj, name, "")
    return value() if callable(value) and name.startswith("get_") else value
