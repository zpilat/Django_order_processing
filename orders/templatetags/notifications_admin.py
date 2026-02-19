from django import template
from orders.models import Notification

register = template.Library()


@register.simple_tag(takes_context=True)
def admin_unacked_notifications_count(context):
    request = context.get('request')
    if not request or not getattr(request, 'user', None) or not request.user.is_authenticated:
        return 0

    return Notification.objects.filter(
        recipient=request.user,
        ack_required=True,
        ack_at__isnull=True,
    ).count()
