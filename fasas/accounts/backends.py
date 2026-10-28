from django.contrib.auth.backends import ModelBackend


class FasasPermissionBackend(ModelBackend):
    """
    Permessi = permessi del ruolo (gruppo) ± permessi personalizzati dell'utente.
    Un override "negato" toglie un permesso anche se il ruolo lo prevede (sezione 26).
    """

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()
        if not hasattr(user_obj, "_fasas_perm_cache"):
            perms = set(super().get_all_permissions(user_obj))
            if not user_obj.is_superuser:
                overrides = user_obj.permission_overrides.values_list(
                    "permission__content_type__app_label", "permission__codename", "allow"
                )
                for app_label, codename, allow in overrides:
                    name = f"{app_label}.{codename}"
                    if allow:
                        perms.add(name)
                    else:
                        perms.discard(name)
            user_obj._fasas_perm_cache = perms
        return user_obj._fasas_perm_cache
