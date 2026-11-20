from django.urls import path

from . import views

urlpatterns = [
    path("csrf", views.csrf, name="signup-csrf"),
    path("signup/email-challenge", views.email_challenge, name="signup-email-challenge"),
    path("signup/email-challenge/verify", views.verify_challenge, name="signup-email-verify"),
    path("signup", views.signup, name="signup"),
]
