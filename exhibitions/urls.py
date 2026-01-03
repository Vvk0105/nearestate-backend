from django.urls import path
from .views import ExhibitorProfileView,  ExhibitorProfileStatusView, AdminUpdateExhibitionView, AdminCreateExhibitionView, AdminDeleteExhibitionView, AdminListExhibitionsView, ExhibitorApplyView, AdminListExhibitorApplications, AdminUpdateExhibitorApplication, PublicExhibitionListView, ExhibitorApplicationStatusView, VisitorRegistration, VisitorQRListView, VisitorRegisterView, AdminQRScanView, ExhibitorCreatePropertyView, ExhibitorMyPropertiesView, ExhibitorDeletePropertyView, PublicExhibitionPropertiesView, PublicExhibitionDetailView, PublicExhibitorsByExhibitionView, VisitorMyRegistrationsView

urlpatterns = [
    path("exhibitor/profile/", ExhibitorProfileView.as_view()),
    path("exhibitor/profile/status/", ExhibitorProfileStatusView.as_view()),
    path("public/exhibitions/", PublicExhibitionListView.as_view()),


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

    path(
    "exhibitor/my-applications/",
    ExhibitorApplicationStatusView.as_view(),
    ),

    path(
    "visitor/register/<int:exhibition_id>/",
    VisitorRegisterView.as_view(),
    ),

    path(
    "visitor/my-qr/",
    VisitorQRListView.as_view(),
    ),

    path(
    "admin/qr/scan/",
    AdminQRScanView.as_view(),
    ),

    path(
    "exhibitor/properties/<int:exhibition_id>/create/",
    ExhibitorCreatePropertyView.as_view(),
    ),

    path(
    "exhibitor/my-properties/",
    ExhibitorMyPropertiesView.as_view(),
    ),

    path(
    "exhibitor/property/<int:property_id>/delete/",
    ExhibitorDeletePropertyView.as_view(),
    ),

    path(
    "public/exhibition/<int:exhibition_id>/properties/",
    PublicExhibitionPropertiesView.as_view(),
    ),

    path(
    "public/exhibitions/<int:id>/",
    PublicExhibitionDetailView.as_view(),
    ),

    path(
    "public/exhibitions/<int:id>/exhibitors/",
    PublicExhibitorsByExhibitionView.as_view(),
    ),

    path(
    "visitor/my-registrations/",
    VisitorMyRegistrationsView.as_view(),
    ),

]
