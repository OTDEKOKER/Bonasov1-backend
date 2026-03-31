from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .report_workbooks import (
    ReportWorkbookExportViewSet,
    ReportWorkbookImportViewSet,
    ReportWorkbookTemplateViewSet,
)

router = DefaultRouter()
router.register("imports", ReportWorkbookImportViewSet, basename="report-workbook-imports")
router.register("templates", ReportWorkbookTemplateViewSet, basename="report-workbook-templates")
router.register("exports", ReportWorkbookExportViewSet, basename="report-workbook-exports")

urlpatterns = [
    path("", include(router.urls)),
]
