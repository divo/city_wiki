from django.urls import path
from . import views

urlpatterns = [
    path('import-city/<str:city_name>/', views.import_city_data, name='import_city_data'),
]
