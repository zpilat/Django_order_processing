from django.conf import settings


def environment_flags(request):
    return {
        "is_debug": bool(settings.DEBUG),
    }
