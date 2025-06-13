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
            ('expedovano', 'Expedováno'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value is None:
            return queryset.filter(expedovano=False)
        elif value == 'expedovano':
            return queryset.filter(expedovano=True)
        return queryset
    
class KompletZakazkaFilter(admin.SimpleListFilter):
    """
    Filtrovat zakázky podle rozpracovanosti a kompletnosti.
    """
    title = "Kompletní"
    parameter_name = "komplet"

    def lookups(self, request, model_admin):
        return (
            ('kompletni', 'Kompletní'),
            ('k_expedici', 'K expedici'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'kompletni':
            # Vrátí zakázky, jejichž všechny bedny jsou ve stavu K expedici nebo Expedováno
            for zakazka in queryset:
                # Zkontroluje, zda má zakázka nějaké bedny a zda všechny bedny v zakázce jsou ve stavu K expedici nebo Expedováno
                if not zakazka.bedny.exists() or not all(bedna.stav_bedny in (StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO)
                                                         for bedna in zakazka.bedny.all()):
                    queryset = queryset.exclude(id=zakazka.id)
        elif value == 'k_expedici':
            # Vrátí zakázky, které mají alespoň jednu bednu ve stavu K expedici
            queryset = queryset.filter(bedny__stav_bedny=StavBednyChoice.K_EXPEDICI).distinct()
        return queryset