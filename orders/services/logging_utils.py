def resolve_actor_name(actor):
    if actor is None:
        return "unknown"
    if hasattr(actor, "is_authenticated"):
        if not actor.is_authenticated:
            return "anonymous"
        if hasattr(actor, "get_username"):
            return actor.get_username()
    return str(actor)


def build_log_context(**kwargs):
    return ", ".join(f"{key}={value}" for key, value in kwargs.items() if value is not None)
