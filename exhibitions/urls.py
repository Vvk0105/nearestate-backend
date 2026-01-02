from django.urls import path
from .views import ExhibitorProfileView,  ExhibitorProfileStatusView, AdminUpdateExhibitionView, AdminCreateExhibitionView, AdminDeleteExhibitionView, AdminListExhibitionsView, ExhibitorApplyView, AdminListExhibitorApplications, AdminUpdateExhibitorApplication

urlpatterns = [
    path("exhibitor/profile/", ExhibitorProfileView.as_view()),
    path("exhibitor/profile/status/", ExhibitorProfileStatusView.as_view()),

    path("admin/exhibitions/", AdminListExhibitionsView.as_view()),
    path("admin/exhibitions/create/", AdminCreateExhibitionView.as_view()),
    path("admin/exhibitions/<int:pk>/update/", AdminUpdateExhibitionView.as_view()),
    path("admin/exhibitions/<int:pk>/delete/", AdminDeleteExhibitionView.as_view()),

    path(
    "exhibitor/apply/<int:exhibition_id>/",
    ExhibitorApplyView.as_view(),
    ),

    path(
    "admin/exhibitor-applications/<int:exhibition_id>/",
    AdminListExhibitorApplications.as_view(),
    ),

    path(
    "admin/exhibitor-application/<int:application_id>/",
    AdminUpdateExhibitorApplication.as_view(),
    ),
]
