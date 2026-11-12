def event_saved(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    from .services import after_event_saved

    after_event_saved(instance, created)


def parameter_saved(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    from fasas.protocols.engine import on_parameter_reading

    if created:
        on_parameter_reading(instance)
