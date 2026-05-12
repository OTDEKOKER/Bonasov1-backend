from decimal import Decimal, InvalidOperation

from aggregates.models import Aggregate
from indicators.models import AssessmentIndicator
from projects.models import ProjectIndicator
from projects.project_indicator_links import ensure_project_indicator_link

from .models import Interaction, Response


AUTO_ROLLUP_NOTES = "[auto-rollup from respondent responses]"


def _has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return any(_has_value(item) for item in value.values())
    return True


def _normalize_token(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value).strip().lower()


def _extract_tokens(value):
    if isinstance(value, list):
        tokens = []
        for item in value:
            tokens.extend(_extract_tokens(item))
        return [token for token in tokens if token]
    if isinstance(value, dict):
        tokens = []
        for item in value.values():
            tokens.extend(_extract_tokens(item))
        return [token for token in tokens if token]
    token = _normalize_token(value)
    return [token] if token else []


def _to_decimal(value):
    if value in (None, ''):
        return Decimal('0')
    if isinstance(value, bool):
        return Decimal('1') if value else Decimal('0')
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        return Decimal('0')


def _sum_numeric(value):
    if isinstance(value, dict):
        if value.get('total') not in (None, ''):
            return _to_decimal(value.get('total'))
        total = Decimal('0')
        for item in value.values():
            total += _sum_numeric(item)
        return total
    if isinstance(value, list):
        total = Decimal('0')
        for item in value:
            total += _sum_numeric(item)
        return total
    return _to_decimal(value)


def _serialize_total(value: Decimal):
    normalized = value.quantize(Decimal('0.01'))
    if normalized == normalized.to_integral():
        return int(normalized)
    return float(normalized)


def _extract_aggregate_total(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, dict):
        if value.get('total') not in (None, ''):
            return Decimal(str(value.get('total')))
        total = Decimal('0')
        for item in value.values():
            total += _extract_aggregate_total(item)
        return total
    return Decimal('0')


def _get_question_config(assessment_id, indicator_id):
    if not assessment_id or not indicator_id:
        return None
    return AssessmentIndicator.objects.filter(
        assessment_id=assessment_id,
        indicator_id=indicator_id,
    ).first()


def _calculate_rollup_value(question, value):
    if question is None:
        return Decimal('0')

    mode = question.aggregate_mode or 'none'
    if mode == 'none':
        return Decimal('0')

    if mode == 'count_all':
        return Decimal('1') if _has_value(value) else Decimal('0')

    if mode == 'sum_numeric':
        return _sum_numeric(value)

    if mode == 'count_selected':
        if not _has_value(value):
            return Decimal('0')

        tokens = _extract_tokens(value)
        match_values = {
            _normalize_token(item) for item in (question.aggregate_match_values or [])
            if _normalize_token(item)
        }
        response_type = question.response_type or question.indicator.type

        if not match_values and response_type == 'yes_no':
            match_values = {'yes', 'true', '1'}

        if match_values:
            return Decimal(str(sum(1 for token in tokens if token in match_values)))

        if isinstance(value, list):
            return Decimal(str(len(tokens)))

        return Decimal('1')

    return Decimal('0')


def sync_rollup_bucket(indicator_id, project_id, organization_id, period_date):
    if not indicator_id or not project_id or not organization_id or not period_date:
        return

    responses = Response.objects.select_related(
        'interaction',
        'interaction__respondent',
    ).filter(
        indicator_id=indicator_id,
        interaction__project_id=project_id,
        interaction__respondent__organization_id=organization_id,
        interaction__date=period_date,
        interaction__assessment_id__isnull=False,
    )

    assessment_ids = {
        response.interaction.assessment_id
        for response in responses
        if response.interaction.assessment_id
    }
    question_map = {
        question.assessment_id: question
        for question in AssessmentIndicator.objects.select_related('indicator').filter(
            assessment_id__in=assessment_ids,
            indicator_id=indicator_id,
        )
    }

    total = Decimal('0')
    for response in responses:
        question = question_map.get(response.interaction.assessment_id)
        total += _calculate_rollup_value(question, response.value)

    aggregate = Aggregate.objects.filter(
        indicator_id=indicator_id,
        project_id=project_id,
        organization_id=organization_id,
        period_start=period_date,
        period_end=period_date,
    ).first()

    if total <= 0:
        if aggregate and aggregate.notes == AUTO_ROLLUP_NOTES:
            aggregate.delete()
    else:
        if aggregate and aggregate.notes != AUTO_ROLLUP_NOTES:
            # Do not overwrite a manually-entered daily aggregate row.
            return

        if aggregate is None:
            creator = responses.first().interaction.created_by if responses.exists() else None
            Aggregate.objects.create(
                indicator_id=indicator_id,
                project_id=project_id,
                organization_id=organization_id,
                period_start=period_date,
                period_end=period_date,
                value=_serialize_total(total),
                status='pending',
                reviewed_at=None,
                reviewed_by=None,
                notes=AUTO_ROLLUP_NOTES,
                created_by=creator,
            )
        else:
            aggregate.value = _serialize_total(total)
            aggregate.notes = AUTO_ROLLUP_NOTES
            aggregate.status = 'pending'
            aggregate.reviewed_at = None
            aggregate.reviewed_by = None
            aggregate.save(update_fields=['value', 'notes', 'status', 'reviewed_at', 'reviewed_by', 'updated_at'])

    sync_project_indicator_total(project_id, indicator_id)


def sync_project_indicator_total(project_id, indicator_id):
    if not project_id or not indicator_id:
        return

    total = Decimal('0')
    for aggregate in Aggregate.objects.filter(
        project_id=project_id,
        indicator_id=indicator_id,
        status='approved',
    ):
        total += _extract_aggregate_total(aggregate.value)

    ensure_project_indicator_link(project_id, indicator_id)
    project_indicator = ProjectIndicator.objects.get(
        project_id=project_id,
        indicator_id=indicator_id,
    )
    normalized_total = total.quantize(Decimal('0.01'))
    if project_indicator.current_value != normalized_total:
        project_indicator.current_value = normalized_total
        project_indicator.save(update_fields=['current_value'])


def sync_response_rollups(response):
    interaction = response.interaction
    organization_id = getattr(interaction.respondent, 'organization_id', None)
    sync_rollup_bucket(
        indicator_id=response.indicator_id,
        project_id=interaction.project_id,
        organization_id=organization_id,
        period_date=interaction.date,
    )


def sync_interaction_rollups(interaction, previous_contexts=None):
    responses = interaction.responses.select_related('interaction__respondent').all()
    current_organization_id = getattr(interaction.respondent, 'organization_id', None)

    for response in responses:
        if previous_contexts:
            for context in previous_contexts:
                sync_rollup_bucket(
                    indicator_id=response.indicator_id,
                    project_id=context.get('project_id'),
                    organization_id=context.get('organization_id'),
                    period_date=context.get('date'),
                )

        sync_rollup_bucket(
            indicator_id=response.indicator_id,
            project_id=interaction.project_id,
            organization_id=current_organization_id,
            period_date=interaction.date,
        )


def sync_assessment_question_rollups(assessment_id, indicator_id):
    contexts = Response.objects.select_related(
        'interaction',
        'interaction__respondent',
    ).filter(
        interaction__assessment_id=assessment_id,
        indicator_id=indicator_id,
    ).values_list(
        'interaction__project_id',
        'interaction__respondent__organization_id',
        'interaction__date',
    ).distinct()

    for project_id, organization_id, period_date in contexts:
        sync_rollup_bucket(
            indicator_id=indicator_id,
            project_id=project_id,
            organization_id=organization_id,
            period_date=period_date,
        )


def get_interaction_rollup_context(interaction_id):
    interaction = Interaction.objects.select_related('respondent').filter(id=interaction_id).first()
    if interaction is None:
        return None
    return {
        'project_id': interaction.project_id,
        'organization_id': interaction.respondent.organization_id if interaction.respondent_id else None,
        'date': interaction.date,
    }
