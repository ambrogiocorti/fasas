"""Turni operatori: mattina, pomeriggio, notte. La notte appartiene alla giornata in cui inizia."""
import datetime

from django.db import models
from django.utils import timezone


class Shift(models.TextChoices):
    MORNING = "M", "Mattina"
    AFTERNOON = "P", "Pomeriggio"
    NIGHT = "N", "Notte"


SHIFT_ORDER = [Shift.MORNING, Shift.AFTERNOON, Shift.NIGHT]


def _config(config=None):
    if config is not None:
        return config
    from .models import SystemConfig

    return SystemConfig.get()


def resolve_shift(moment=None, config=None):
    """Restituisce (giornata_di_turno, turno) per un istante."""
    config = _config(config)
    moment = timezone.localtime(moment or timezone.now())
    t = moment.time()
    day = moment.date()
    if config.morning_start <= t < config.afternoon_start:
        return day, Shift.MORNING
    if config.afternoon_start <= t < config.night_start:
        return day, Shift.AFTERNOON
    if t >= config.night_start:
        return day, Shift.NIGHT
    return day - datetime.timedelta(days=1), Shift.NIGHT


def shift_bounds(day, shift, config=None):
    """Inizio e fine (aware, ora locale) di un turno."""
    config = _config(config)
    tz = timezone.get_current_timezone()

    def at(d, t):
        return timezone.make_aware(datetime.datetime.combine(d, t), tz)

    if shift == Shift.MORNING:
        return at(day, config.morning_start), at(day, config.afternoon_start)
    if shift == Shift.AFTERNOON:
        return at(day, config.afternoon_start), at(day, config.night_start)
    return at(day, config.night_start), at(day + datetime.timedelta(days=1), config.morning_start)


def shift_label(shift):
    return Shift(shift).label


def previous_shift(day, shift):
    index = SHIFT_ORDER.index(shift)
    if index == 0:
        return day - datetime.timedelta(days=1), Shift.NIGHT
    return day, SHIFT_ORDER[index - 1]


def time_in_shift(t, shift, config=None):
    """True se l'orario (time) di una somministrazione programmata cade nel turno."""
    config = _config(config)
    if shift == Shift.MORNING:
        return config.morning_start <= t < config.afternoon_start
    if shift == Shift.AFTERNOON:
        return config.afternoon_start <= t < config.night_start
    return t >= config.night_start or t < config.morning_start


def scheduled_moment(day, shift, t, config=None):
    """Istante reale di un orario programmato all'interno di un turno (la notte scavalca la mezzanotte)."""
    config = _config(config)
    tz = timezone.get_current_timezone()
    actual_day = day
    if shift == Shift.NIGHT and t < config.morning_start:
        actual_day = day + datetime.timedelta(days=1)
    return timezone.make_aware(datetime.datetime.combine(actual_day, t), tz)
