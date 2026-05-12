from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db.models import Q

from organizations.access import get_user_organization_ids
from users.models import User

from .models import Notification

AGGREGATE_AWAITING_REVIEW_TITLE = "Aggregate awaiting review"


@dataclass(frozen=True)
class AggregateNotificationContext:
    aggregate_id: int
    organization_id: int
    indicator_label: str
    organization_name: str
    period_start: str
    period_end: str


def _display_name(user: User | None) -> str:
    if not user:
        return "A user"
    full_name = user.full_name.strip()
    return full_name or user.username or "A user"


def _build_aggregate_link(aggregate_id: int) -> str:
    return f"/aggregates?reviewAggregateId={aggregate_id}"


def _resolve_reviewer_users(organization_id: int, exclude_user_ids: Iterable[int] | None = None) -> list[User]:
    excluded = {int(user_id) for user_id in (exclude_user_ids or [])}
    recipients_by_id: dict[int, User] = {}

    admin_users = User.objects.filter(is_active=True).filter(
        Q(is_superuser=True) | Q(is_staff=True) | Q(role="admin"),
    )
    for user in admin_users:
        if user.id in excluded:
            continue
        recipients_by_id[user.id] = user

    manager_users = (
        User.objects.filter(is_active=True, role="manager")
        .exclude(organization_id__isnull=True)
        .select_related("organization")
    )
    for user in manager_users:
        if user.id in excluded:
            continue
        try:
            visible_org_ids = get_user_organization_ids(user)
        except Exception:
            visible_org_ids = []
        if organization_id in visible_org_ids:
            recipients_by_id[user.id] = user

    return list(recipients_by_id.values())


def get_reviewer_users_for_organization(
    organization_id: int,
    *,
    exclude_user_ids: Iterable[int] | None = None,
) -> list[User]:
    return _resolve_reviewer_users(
        organization_id=organization_id,
        exclude_user_ids=exclude_user_ids,
    )


def get_aggregate_review_link(aggregate_id: int) -> str:
    return _build_aggregate_link(aggregate_id)


def build_aggregate_awaiting_review_content(
    *,
    context: AggregateNotificationContext,
    actor: User | None,
) -> str:
    return (
        f"{_display_name(actor)} submitted {context.indicator_label} for "
        f"{context.organization_name} ({context.period_start} to {context.period_end})."
    )


def _bulk_create_notifications(*, recipients: list[User], title: str, content: str, link: str) -> None:
    if not recipients:
        return
    Notification.objects.bulk_create(
        [
            Notification(
                user=recipient,
                title=title,
                content=content,
                link=link,
            )
            for recipient in recipients
        ],
    )


def notify_aggregate_submitted_for_review(
    *,
    context: AggregateNotificationContext,
    actor: User | None,
) -> None:
    recipients = _resolve_reviewer_users(
        organization_id=context.organization_id,
        exclude_user_ids=[actor.id] if actor else None,
    )
    title = AGGREGATE_AWAITING_REVIEW_TITLE
    content = build_aggregate_awaiting_review_content(
        context=context,
        actor=actor,
    )
    _bulk_create_notifications(
        recipients=recipients,
        title=title,
        content=content,
        link=_build_aggregate_link(context.aggregate_id),
    )


def notify_aggregate_status_to_submitter(
    *,
    context: AggregateNotificationContext,
    actor: User | None,
    submitter: User | None,
    status_value: str,
) -> None:
    if not submitter or not submitter.is_active:
        return
    if actor and submitter.id == actor.id:
        return

    status_copy = {
        "reviewed": ("Aggregate reviewed", "reviewed and is ready for approval"),
        "approved": ("Aggregate approved", "approved"),
        "flagged": ("Aggregate flagged", "flagged for correction"),
        "rejected": ("Aggregate rejected", "rejected"),
        "pending": ("Aggregate queued", "queued for review"),
    }
    title, action_text = status_copy.get(status_value, ("Aggregate updated", "updated"))
    content = (
        f"{context.indicator_label} for {context.organization_name} "
        f"({context.period_start} to {context.period_end}) was {action_text} by {_display_name(actor)}."
    )
    Notification.objects.create(
        user=submitter,
        title=title,
        content=content,
        link=_build_aggregate_link(context.aggregate_id),
    )
