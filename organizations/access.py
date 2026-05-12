from __future__ import annotations

from typing import Iterable


def get_user_organization_ids(user) -> list[int]:
    if not getattr(user, "organization_id", None):
        return []

    organization = user.organization
    descendants = organization.get_descendants()
    return [organization.id] + [child.id for child in descendants]


def is_organization_admin(user) -> bool:
    return bool(user and (user.is_superuser or user.is_staff or user.role == "admin"))


def filter_queryset_by_org_ids(queryset, field_name: str, org_ids: Iterable[int]):
    org_ids = list(org_ids)
    if not org_ids:
        return queryset.none()
    return queryset.filter(**{f"{field_name}__in": org_ids})
