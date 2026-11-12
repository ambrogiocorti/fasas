"""
Serializzazione JSON esatta, usata dai backup senza PostgreSQL (manage.py dumpdata --format fasasjson).

Il JSON di Django tronca ore e date ai millisecondi: un backup ripristinato avrebbe orari diversi di qualche
microsecondo e l'impronta delle voci di audit non tornerebbe più. Qui si conservano i microsecondi.
"""
import datetime

from django.core.serializers.json import (
    Deserializer,  # noqa: F401 - la lettura è quella standard
    DjangoJSONEncoder,
)
from django.core.serializers.json import Serializer as DjangoSerializer


class ExactEncoder(DjangoJSONEncoder):
    def default(self, o):
        if isinstance(o, (datetime.datetime, datetime.time)):
            return o.isoformat()
        return super().default(o)


class Serializer(DjangoSerializer):
    def _init_options(self):
        super()._init_options()
        self.json_kwargs["cls"] = ExactEncoder
