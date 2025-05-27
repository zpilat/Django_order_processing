from django.contrib import admin
from .models import StavBednyChoice, Zakazka, Bedna

class StavBednyFilter(admin.SimpleListFilter):
    """
    Filtrovat bedny podle stavu.
    """
    title = "Stav bedny"
    parameter_name = "stav_bedny_vlastni"

    def lookups(self, request, model_admin):
        # všechny hodnoty z choices (+ Nezpracováno)
        #result = [('NEZPRACOVANO', "Nezpracováno")]
        result = []
        for value, label in StavBednyChoice.choices:
            result.append((value, label))
        return result

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
        # elif value == 'NEZPRACOVANO':
        #     return queryset.filter(stav_bedny__in=[StavBednyChoice.PRIJATO, StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI])
        return queryset.filter(stav_bedny=value)
        

class ExpedovanaZakazkaFilter(admin.SimpleListFilter):
    """
    Filtrovat zakázky podle stavu expedice.
    """
    title = "Skladem"
    parameter_name = "skladem"

    def lookups(self, request, model_admin):
        return (
            ('Expedováno', 'Expedováno'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.filter(expedovano=False)
        elif value == 'Expedováno':
            return queryset.filter(expedovano=True)
        return queryset