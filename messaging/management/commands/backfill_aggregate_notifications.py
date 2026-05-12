from __future__ import annotations

from typing import Iterable

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from aggregates.models import Aggregate
from messaging.models import Notification
from messaging.notifications import (
    AGGREGATE_AWAITING_REVIEW_TITLE,
    AggregateNotificationContext,
    build_aggregate_awaiting_review_content,
    get_aggregate_review_link,
    get_reviewer_users_for_organization,
)


class Command(BaseCommand):
    help = "Backfill reviewer notifications for existing aggregate submissions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            default="pending",
            help="Comma-separated aggregate statuses to include (default: pending).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview records that would be created without writing notifications.",
        )

    def _parse_statuses(self, raw_statuses: str) -> list[str]:
        statuses = [value.strip() for value in str(raw_statuses).split(",") if value.strip()]
        if not statuses:
            raise CommandError("No statuses provided. Example: --status pending,reviewed")
        invalid = [status for status in statuses if status not in {choice for choice, _ in Aggregate.STATUS_CHOICES}]
        if invalid:
            raise CommandError(f"Invalid status value(s): {', '.join(invalid)}")
        return statuses

    def _context_for(self, aggregate: Aggregate) -> AggregateNotificationContext:
        indicator_label = (
            (getattr(aggregate.indicator, "code", None) or "").strip()
            or (getattr(aggregate.indicator, "name", None) or "").strip()
            or f"Indicator {aggregate.indicator_id}"
        )
        organization_name = (
            (getattr(aggregate.organization, "name", None) or "").strip()
            or f"Organization {aggregate.organization_id}"
        )
        return AggregateNotificationContext(
            aggregate_id=int(aggregate.id),
            organization_id=int(aggregate.organization_id),
            indicator_label=indicator_label,
            organization_name=organization_name,
            period_start=aggregate.period_start.isoformat() if aggregate.period_start else "",
            period_end=aggregate.period_end.isoformat() if aggregate.period_end else "",
        )

    def _existing_keys_for_link(self, link: str) -> set[tuple[int, str, str]]:
        rows = Notification.objects.filter(link=link).values_list("user_id", "title", "link")
        return {(int(user_id), str(title), str(url)) for user_id, title, url in rows}

    def _recipient_ids(self, aggregate: Aggregate) -> Iterable[int]:
        exclude_ids = [int(aggregate.created_by_id)] if aggregate.created_by_id else None
        recipients = get_reviewer_users_for_organization(
            int(aggregate.organization_id),
            exclude_user_ids=exclude_ids,
        )
        return [int(user.id) for user in recipients if user and user.is_active]

    def handle(self, *args, **options):
        statuses = self._parse_statuses(options["status"])
        dry_run = bool(options["dry_run"])

        queryset = (
            Aggregate.objects.filter(status__in=statuses)
            .select_related("indicator", "organization", "created_by")
            .order_by("id")
        )

        created = 0
        skipped_existing = 0
        missing_recipients = 0
        aggregate_rows = 0

        for aggregate in queryset.iterator(chunk_size=500):
            aggregate_rows += 1
            context = self._context_for(aggregate)
            link = get_aggregate_review_link(context.aggregate_id)
            content = build_aggregate_awaiting_review_content(context=context, actor=aggregate.created_by)
            recipient_ids = list(self._recipient_ids(aggregate))

            if not recipient_ids:
                missing_recipients += 1
                continue

            existing_keys = self._existing_keys_for_link(link)
            to_create: list[Notification] = []
            for user_id in recipient_ids:
                key = (user_id, AGGREGATE_AWAITING_REVIEW_TITLE, link)
                if key in existing_keys:
                    skipped_existing += 1
                    continue
                to_create.append(
                    Notification(
                        user_id=user_id,
                        title=AGGREGATE_AWAITING_REVIEW_TITLE,
                        content=content,
                        link=link,
                    )
                )

            if not to_create:
                continue

            if dry_run:
                created += len(to_create)
                continue

            with transaction.atomic():
                Notification.objects.bulk_create(to_create)
            created += len(to_create)

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Aggregate rows scanned: {aggregate_rows}"))
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Notifications to create/created: {created}"))
        self.stdout.write(self.style.WARNING(f"[{mode}] Skipped existing notifications: {skipped_existing}"))
        self.stdout.write(self.style.WARNING(f"[{mode}] Aggregates with no eligible recipients: {missing_recipients}"))
