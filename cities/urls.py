from django.urls import path
from . import views

urlpatterns = [
    path('', views.city_list, name='city_list'),
    path('city/<str:city_name>/', views.city_detail, name='city_detail'),
    path('import-city/<str:city_name>/', views.import_city_data, name='import_city_data'),
]
