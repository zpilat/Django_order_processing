from django.urls import path
from .views import (
    BednyListView,
    dashboard_bedny_view,
    dashboard_kamiony_view,
    dashboard_vyroba_view,
    dashboard_bedny_k_navezeni_view,
    dashboard_bedny_k_navezeni_pdf_view,
    dashboard_bedny_k_navezeni_poznamka_view,
    protokol_kamion_vydej_pdf_view,
    dodaci_list_kamion_vydej_pdf_view,
    proforma_kamion_vydej_pdf_view,
)

urlpatterns = [
    path('dashboard/bedny/', dashboard_bedny_view, name='dashboard_bedny'),
    path('dashboard/kamiony/', dashboard_kamiony_view, name='dashboard_kamiony'),    
    path('dashboard/vyroba/', dashboard_vyroba_view, name='dashboard_vyroba'),
    path('bedny/', BednyListView.as_view(), name='bedny_list'),
    path('bedny/k-navezeni/', dashboard_bedny_k_navezeni_view, name='dashboard_bedny_k_navezeni'),
    path('bedny/k-navezeni/poznamka/', dashboard_bedny_k_navezeni_poznamka_view, name='dashboard_bedny_k_navezeni_poznamka'),
    path('bedny/k-navezeni/pdf/', dashboard_bedny_k_navezeni_pdf_view, name='dashboard_bedny_k_navezeni_pdf'),
    path('protokol/kamion-vydej/<int:pk>/', protokol_kamion_vydej_pdf_view, name='protokol_kamion_vydej_pdf'),
    path('dodaci-list/kamion-vydej/<int:pk>/', dodaci_list_kamion_vydej_pdf_view, name='dodaci_list_kamion_vydej_pdf'),
    path('proforma/kamion-vydej/<int:pk>/', proforma_kamion_vydej_pdf_view, name='proforma_kamion_vydej_pdf'),
]
