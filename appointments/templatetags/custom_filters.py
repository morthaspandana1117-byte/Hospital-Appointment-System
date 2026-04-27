from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    return dictionary.get(key, 0)


@register.filter
def status_badge(status):
    """
    Returns the CSS class for status badge styling.
    Maps status to appropriate CSS class.
    """
    status_mapping = {
        "Requested": "status-requested",
        "Assigned": "status-assigned",
        "Accepted": "status-accepted",
        "Completed": "status-completed",
        "Cancelled": "status-cancelled",
        # Legacy status support
        "Pending": "status-requested",
        "Rejected": "status-cancelled",
        "Confirmed": "status-accepted",
    }
    return status_mapping.get(status, "status-default")


@register.simple_tag
def can_cancel(appointment, user):
    """
    Check if user can cancel the appointment.
    Returns True if the appointment status allows cancellation.
    """
    if appointment.can_transition_to("Cancelled"):
        return True
    return False


@register.simple_tag
def can_complete(appointment):
    """
    Check if appointment can be marked as completed.
    """
    if appointment.can_transition_to("Completed"):
        return True
    return False


@register.simple_tag
def can_accept(appointment):
    """
    Check if appointment can be accepted.
    """
    if appointment.can_transition_to("Accepted"):
        return True
    return False