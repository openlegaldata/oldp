from django.urls import re_path

from . import views

app_name = "contact"
urlpatterns = [
    re_path(r"^$", views.form_view, name="form"),
    re_path(r"^report_content$", views.report_content_view, name="report_content"),
    re_path(r"^thankyou", views.thankyou_view, name="thankyou"),
]
