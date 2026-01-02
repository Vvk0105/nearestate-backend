from django.urls import path
from .views import ExhibitorProfileView,  ExhibitorProfileStatusView

urlpatterns = [
    path("exhibitor/profile/", ExhibitorProfileView.as_view()),
    path("exhibitor/profile/status/", ExhibitorProfileStatusView.as_view()),

]
