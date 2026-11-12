def evacuation_saved(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    from fasas.protocols.engine import on_evacuation

    if created:
        on_evacuation(instance)
