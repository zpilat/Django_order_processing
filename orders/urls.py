from django.urls import path
from .views import BednyListView, dashboard_bedny_view, dashboard_kamiony_view, dashboard_bedny_k_navezeni_view

urlpatterns = [
    path('dashboard/bedny/', dashboard_bedny_view, name='dashboard_bedny'),
    path('dashboard/kamiony/', dashboard_kamiony_view, name='dashboard_kamiony'),    
    path('bedny/', BednyListView.as_view(), name='bedny_list'),
    path('bedny/k-navezeni/', dashboard_bedny_k_navezeni_view, name='dashboard_bedny_k_navezeni'),
]
