from django.urls import path

from apps.it_support.views import PasswordResetViewSet, SupportTicketViewSet

ticket_list = SupportTicketViewSet.as_view({'get': 'list', 'post': 'create'})
ticket_detail = SupportTicketViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'})
reset_password_view = PasswordResetViewSet.as_view({'post': 'reset_password'})

urlpatterns = [
    path('support-tickets/', ticket_list, name='support-ticket-list'),
    path('support-tickets/<uuid:pk>/', ticket_detail, name='support-ticket-detail'),
    path('support/reset-password/', reset_password_view, name='support-reset-password'),
]
