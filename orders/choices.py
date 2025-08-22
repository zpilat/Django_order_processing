from django.db import models
from django.utils.translation import gettext_lazy as _

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
    ROVNA_SE = 'RS', 'Rovná se'
    VYROVNANA = 'VY', 'Vyrovnaná'

class TryskaniChoice(models.TextChoices):
    NEZADANO = '--', '--------'
    CISTA = 'CI', 'Čistá'
    SPINAVA = 'SP', 'Špinavá'
    OTRYSKANA = 'OT', 'Otryskaná'

class PrioritaChoice(models.TextChoices):
    VYSOKA = 'P1', 'P1'
    STREDNI = 'P2', 'P2'
    NIZKA = 'P3', '--'

class KamionChoice(models.TextChoices):
    PRIJEM = 'P', 'Přijem'
    VYDEJ = 'V', 'Výdej'

class KodChoice(models.TextChoices):
    A = 'A', 'A'
    B = 'B', 'B'
    C = 'C', 'C'
    D = 'D', 'D'
    E = 'E', 'E'
    F = 'F', 'F'
    G = 'G', 'G'
    H = 'H', 'H'
    I = 'I', 'I'
    J = 'J', 'J'
    K = 'K', 'K'
    L = 'L', 'L'
    M = 'M', 'M'
    N = 'N', 'N'
    O = 'O', 'O'
    P = 'P', 'P'
    Q = 'Q', 'Q'
    R = 'R', 'R'
    S = 'S', 'S'
    T = 'T', 'T'
    U = 'U', 'U'
    V = 'V', 'V'
    W = 'W', 'W'
    X = 'X', 'X'
    Y = 'Y', 'Y'
    Z = 'Z', 'Z'
