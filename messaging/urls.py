from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("messages/", views.conversation_list, name="list"),
    path("messages/<int:conversation_id>/", views.conversation_detail, name="conversation"),
    path("messages/<int:conversation_id>/send/", views.send_message, name="send"),
    path("messages/start/<int:user_id>/", views.start_conversation, name="start"),
]
