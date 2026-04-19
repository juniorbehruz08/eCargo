from django.urls import path
from .views import *

urlpatterns = [
    # ── Core ──────────────────────────────────────
    path('', main, name='main'),
    path('login/', login_view, name='login'),
    path('send_code/', send_code, name='send_code'),
    path('verify_email/', verify_email, name='verify_email'),

    # ── Loads ─────────────────────────────────────
    path('load_list/', load_list, name='load_list'),
    path('add/', add_load, name='add_load'),
    path('save/', save_load, name='save_load'),
    path('<int:pk>/', load_detail, name='load_detail'),
    path('<int:pk>/delete/', delete_load, name='delete_load'),

    # ── Live API ──────────────────────────────────
    path('api/loads/', load_api_list, name='load_api_list'),

    # ── Interests ─────────────────────────────────
    path('interest/<int:load_pk>/', express_interest, name='express_interest'),  # POST: carrier expresses interest
    path('interests/', interests_page, name='interests_page'),  # GET: shipper sees all interests
    path('interest/<int:interest_pk>/accept/', accept_interest, name='accept_interest'),  # POST: shipper accepts
    path('interest/<int:interest_pk>/reject/', reject_interest, name='reject_interest'),  # POST: shipper rejects

    # ── Notifications ──────────────────────────────
    path('api/notifications/', notifications_api, name='notifications_api'),
    path('api/notifications/read/', mark_notifications_read, name='mark_notifications_read'),

    # ── Chat ───────────────────────────────────────
    path('chats/', my_chats, name='my_chats'),  # list of chat rooms
    path('chat/<int:room_pk>/', chat_view, name='chat_view'),  # single chat room
    path('chat/<int:room_pk>/send/', send_message, name='send_message'),  # POST: send a message
    path('chat/<int:room_pk>/poll/', poll_messages, name='poll_messages'),  # GET: poll new messages
    path('carrier/<int:carrier_pk>/', carrier_info, name='carrier_info')
]
