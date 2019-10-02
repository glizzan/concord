from django.urls import path

from . import views

app_name = 'communities'

urlpatterns = [

    # Leadership update views
    path('leadership/owners/<int:community_pk>/', views.update_owners, 
        name='update_owners'),
    path('leadership/owner_condition/<int:community_pk>/', 
        views.update_owner_condition, name='update_owner_condition'),
    path('leadership/governors/<int:community_pk>/', views.update_governors, 
        name='update_governors'),
    path('leadership/governor_condition/<int:community_pk>/', 
        views.update_governors, name='update_governor_condition'),    
        
]