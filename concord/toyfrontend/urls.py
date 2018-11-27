from django.urls import path

from . import views

urlpatterns = [
    path('', views.ResourceListView.as_view(), name='resource_list'),
    path('owner/<owner_name>/', views.ResourceListByOwnerView.as_view(), name='resource_list_by_owner'),
    path('resource/<pk>/', views.ResourceDetailView.as_view(), name='resource_detail'),

]