from django.urls import path

from . import views

app_name = "marketplace"

urlpatterns = [
    path("tutors/<slug:tutor_slug>/enquire/", views.send_enquiry, name="send_enquiry"),
    path("tutors/<slug:tutor_slug>/demo/", views.request_demo, name="request_demo"),
    path("tutors/id/<int:tutor_id>/save/", views.toggle_save_tutor, name="toggle_save"),
    path("student/enquiries/", views.enquiry_list, name="enquiry_list"),
    path("student/enquiries/<int:enquiry_id>/withdraw/", views.withdraw_enquiry, name="withdraw_enquiry"),
    path("student/enquiries/<int:enquiry_id>/close/", views.close_enquiry, name="close_enquiry"),
    path("parent/enquiries/", views.enquiry_list, name="parent_enquiries"),
    path("tutor/enquiries/", views.tutor_enquiry_list, name="tutor_enquiries"),
    path("tutor/enquiries/<int:enquiry_id>/respond/", views.respond_enquiry, name="respond_enquiry"),
    # Tutor requests
    path("requests/", views.request_browse, name="request_browse"),
    path("requests/<int:request_id>/", views.request_detail, name="request_detail"),
    path("student/requests/", views.my_requests, name="my_requests"),
    path("student/requests/new/", views.request_create, name="request_create"),
    path("student/requests/<int:request_id>/close/", views.request_close, name="request_close"),
    path("parent/requests/", views.my_requests, name="parent_requests"),
    path("parent/requests/new/", views.request_create, name="parent_request_create"),
    path("tutor/requests/", views.request_browse, name="tutor_requests"),
    path("requests/<int:request_id>/apply/", views.apply_to_request, name="apply"),
    path("applications/<int:application_id>/respond/", views.respond_application, name="respond_application"),
]
