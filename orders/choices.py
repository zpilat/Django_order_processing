from django.db import models
from django.utils.translation import gettext_lazy as _

class TypHlavyChoice(models.TextChoices):
    TK = 'TK', 'TK'
    SK = 'SK', 'SK'
    ZK = 'ZK', 'ZK'

class StavBednyChoice(models.TextChoices):
    PRIJATO = 'PR', 'Přijato'
    K_NAVEZENI = 'KN', 'K navezení'
    NAVEZENO = 'NA', 'Navezeno'
    DO_ZPRACOVANI = 'DZ', 'Do zpracování'
    ZAKALENO = 'ZA', 'Zakaleno'
    ZKONTROLOVANO = 'ZK', 'Zkontrolováno'
    K_EXPEDICI = 'KE', 'K expedici'
    EXPEDOVANO = 'EX', 'Expedováno'

class RovnaniChoice(models.TextChoices):
    NEZADANO = '--', '--------'
    ROVNA = 'RO', 'Rovná'
    KRIVA = 'KR', 'Křivá'
    VYROVNANA = 'VY', 'Vyrovnaná'

class TryskaniChoice(models.TextChoices):
    NEZADANO = '--', '--------'
    CISTA = 'CI', 'Čistá'
    SPINAVA = 'SP', 'Špinavá'
    OTRYSKANA = 'OT', 'Otryskaná'

class PrioritaChoice(models.TextChoices):
    NIZKA = '-', 'Nízká'
    STREDNI = 'P2', 'Střední P2'
    VYSOKA = 'P1', 'Vysoká P1'

class KamionChoice(models.TextChoices):
    PRIJEM = 'P', 'Přijem'
    VYDEJ = 'V', 'Výdej'