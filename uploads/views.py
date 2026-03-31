import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from rest_framework.decorators import action
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone

from core.permissions import is_platform_admin
from indicators.models import Indicator
from organizations.models import Organization
from projects.models import Project, ProjectIndicator, ProjectIndicatorOrganizationTarget

from .models import Upload, ImportJob
from .serializers import (
    UploadSerializer,
    ImportJobSerializer,
    CreateMissingIndicatorsSerializer,
)


ORGANIZATION_NAME_ALIASES = {
    "masego mental health org": "masego mental health",
    "the just hope foundation": "just hope foundation",
    "vmf valour": "valour mental health",
    "stop smoking support group": "sssg",
    "the fighters support group": "tfsg",
    "botswana network for mental health bonmeh": "bonmeh",
}


def _normalize_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return re.sub(r"\s+", " ", normalized)


def _organization_tokens(value: str) -> set[str]:
    return {token for token in _normalize_text(value).split() if token}


def _organization_variants(value: str) -> list[str]:
    normalized = _normalize_text(value)
    variants = {normalized}
    if normalized in ORGANIZATION_NAME_ALIASES:
        variants.add(_normalize_text(ORGANIZATION_NAME_ALIASES[normalized]))
    if normalized.startswith("the "):
        variants.add(normalized[4:])
    if normalized.endswith(" org"):
        variants.add(normalized[:-4].strip())
    return [variant for variant in variants if variant]


def _sanitize_indicator_code(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '-', str(value or '').strip().upper()).strip('-_')
    return (cleaned or 'INDICATOR')[:50]


def _build_unique_indicator_code(requested_code: str) -> str:
    base = _sanitize_indicator_code(requested_code)
    candidate = base
    suffix = 2
    while Indicator.objects.filter(code__iexact=candidate).exists():
        candidate = f"{base[: max(1, 50 - len(str(suffix)) - 1)]}-{suffix}"
        suffix += 1
    return candidate


def _to_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _resolve_assignment_organization(assignment: dict) -> Organization | None:
    organization_id = assignment.get("organization_id")
    if organization_id:
        return Organization.objects.filter(id=organization_id).first()

    organization_name = str(assignment.get("organization_name") or "").strip()
    if not organization_name:
        return None

    organizations = list(Organization.objects.all())
    indexed_matches = {}
    for organization in organizations:
        keys = {
            _normalize_text(organization.name),
            _normalize_text(organization.code),
        }
        keys.update(_organization_variants(organization.name))
        indexed_matches[organization.id] = (organization, keys, _organization_tokens(organization.name))

    for variant in _organization_variants(organization_name):
        exact = [
            organization
            for organization, keys, _ in indexed_matches.values()
            if variant in keys
        ]
        if exact:
            return exact[0]

    requested_tokens = _organization_tokens(organization_name)
    ranked = []
    for organization, _, tokens in indexed_matches.values():
        overlap = len(requested_tokens & tokens)
        if overlap:
            ranked.append((overlap, len(tokens), organization))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2].name.lower()))
    return ranked[0][2] if ranked else None


class UploadViewSet(viewsets.ModelViewSet):
    """ViewSet for managing uploads."""
    
    queryset = Upload.objects.all()
    serializer_class = UploadSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['file_type', 'organization', 'content_type']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return Upload.objects.all()
        elif user.organization:
            return Upload.objects.filter(organization=user.organization)
        return Upload.objects.filter(created_by=user)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @action(detail=True, methods=['post'])
    def start_import(self, request, pk=None):
        """Start an import job for the uploaded file."""
        upload = self.get_object()
        
        # Create import job
        job = ImportJob.objects.create(
            upload=upload,
            created_by=request.user
        )
        
        # In production, this would trigger a background task
        # For now, return the job status
        return Response(ImportJobSerializer(job).data, status=status.HTTP_201_CREATED)


class ImportJobViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing import jobs."""
    
    queryset = ImportJob.objects.all()
    serializer_class = ImportJobSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'upload']
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_staff or user.role == 'admin':
            return ImportJob.objects.all()
        return ImportJob.objects.filter(created_by=user)

    @action(detail=True, methods=['post'], url_path='create-missing-indicators')
    def create_missing_indicators(self, request, pk=None):
        """Create workbook-derived indicators, assign them to a project, and create org targets."""
        if not is_platform_admin(request.user):
            return Response(
                {"detail": "Admin privileges are required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        job = self.get_object()
        serializer = CreateMissingIndicatorsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        assign_to_project = payload.get("assign_to_project", True)
        create_targets = payload.get("create_targets", True)
        project_id = payload.get("project_id")

        project = None
        if assign_to_project or create_targets:
            if not project_id:
                return Response(
                    {"detail": "project_id is required when assigning indicators or creating targets."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            project = Project.objects.filter(id=project_id).first()
            if not project:
                return Response(
                    {"detail": "Project not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        created_items = []
        warnings = []

        with transaction.atomic():
            for item in payload["indicators"]:
                requested_name = item["name"].strip()
                requested_code = _sanitize_indicator_code(item["code"])
                indicator = Indicator.objects.filter(code__iexact=requested_code).first()
                created = False

                if not indicator:
                    indicator = Indicator.objects.filter(name__iexact=requested_name).first()

                if not indicator:
                    indicator = Indicator.objects.create(
                        name=requested_name,
                        code=_build_unique_indicator_code(requested_code),
                        type=item.get("type") or "number",
                        category=item.get("category") or "ncd",
                        unit=item.get("unit", ""),
                        sub_labels=item.get("sub_labels") or [],
                        aggregate_disaggregation_config=item.get("aggregate_disaggregation_config") or {},
                        created_by=request.user,
                    )
                    created = True
                else:
                    updated_fields = []
                    if item.get("sub_labels") and not list(indicator.sub_labels or []):
                        indicator.sub_labels = item.get("sub_labels") or []
                        updated_fields.append("sub_labels")
                    if (
                        item.get("aggregate_disaggregation_config")
                        and not dict(indicator.aggregate_disaggregation_config or {})
                    ):
                        indicator.aggregate_disaggregation_config = (
                            item.get("aggregate_disaggregation_config") or {}
                        )
                        updated_fields.append("aggregate_disaggregation_config")
                    if updated_fields:
                        indicator.save(update_fields=updated_fields)

                resolved_organizations = {}
                for org_id in item.get("organizations", []):
                    organization = Organization.objects.filter(id=org_id).first()
                    if organization:
                        resolved_organizations[str(organization.id)] = organization

                assignment_results = []
                for assignment in item.get("assignments", []):
                    organization = _resolve_assignment_organization(assignment)
                    if not organization:
                        warnings.append(
                            {
                                "temp_key": item["temp_key"],
                                "indicator_name": requested_name,
                                "message": f"Could not resolve organization for assignment: {assignment!r}",
                            }
                        )
                        continue
                    resolved_organizations[str(organization.id)] = organization
                    assignment_results.append(
                        {
                            "organization_id": organization.id,
                            "organization_name": organization.name,
                            "q1_target": str(_to_decimal(assignment.get("q1_target"))),
                            "q2_target": str(_to_decimal(assignment.get("q2_target"))),
                            "q3_target": str(_to_decimal(assignment.get("q3_target"))),
                            "q4_target": str(_to_decimal(assignment.get("q4_target"))),
                        }
                    )

                if resolved_organizations:
                    indicator.organizations.add(*resolved_organizations.values())
                    if project:
                        project.organizations.add(*resolved_organizations.values())

                project_indicator = None
                if assign_to_project and project:
                    project_indicator, _ = ProjectIndicator.objects.get_or_create(
                        project=project,
                        indicator=indicator,
                    )

                if create_targets and project_indicator:
                    for assignment in item.get("assignments", []):
                        organization = _resolve_assignment_organization(assignment)
                        if not organization:
                            continue
                        org_target, _ = ProjectIndicatorOrganizationTarget.objects.get_or_create(
                            project_indicator=project_indicator,
                            organization=organization,
                        )
                        org_target.q1_target = _to_decimal(assignment.get("q1_target"))
                        org_target.q2_target = _to_decimal(assignment.get("q2_target"))
                        org_target.q3_target = _to_decimal(assignment.get("q3_target"))
                        org_target.q4_target = _to_decimal(assignment.get("q4_target"))
                        org_target.save()

                created_items.append(
                    {
                        "temp_key": item["temp_key"],
                        "indicator_id": indicator.id,
                        "name": indicator.name,
                        "code": indicator.code,
                        "created": created,
                        "project_assigned": bool(project_indicator),
                        "assigned_organizations": [
                            {"id": organization.id, "name": organization.name}
                            for organization in resolved_organizations.values()
                        ],
                        "targets": assignment_results,
                    }
                )

        job.errors = [
            *list(job.errors or []),
            *(
                [{"type": "missing_indicator_warning", **warning} for warning in warnings]
                if warnings
                else []
            ),
        ]
        job.save(update_fields=["errors"])

        return Response(
            {
                "import_job_id": job.id,
                "project_id": project.id if project else None,
                "created_count": sum(1 for item in created_items if item["created"]),
                "resolved_count": len(created_items),
                "warnings": warnings,
                "results": created_items,
            },
            status=status.HTTP_200_OK,
        )

