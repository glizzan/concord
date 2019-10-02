from django.urls import path

from . import views

app_name = 'conditionals'

urlpatterns = [

    # General condition views
    path('conditions/<int:action_pk>/', views.condition_landing_view, name='condition_detail'),

    # Approval condition views
    path('conditions/approve/<int:action_pk>/', views.approve_action, name='approve_action'),
    path('conditions/reject/<int:action_pk>/', views.reject_action, name='reject_action'),

    # Vote condition views
    path('conditions/cast_vote/<int:action_pk>/<selection>/', views.cast_vote, name='cast_vote'),

]