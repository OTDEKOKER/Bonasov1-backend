from django.db import transaction
from organizations.models import Organization
from indicators.models import Indicator, Assessment, AssessmentIndicator
from projects.models import Project, ProjectIndicator, Task
import re


def make_code(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).upper().strip("_")
    if not base:
        base = "INDICATOR"
    if len(base) > 50:
        base = base[:50].rstrip("_")
    code = base
    suffix = 2
    while Indicator.objects.filter(code=code).exists():
        trimmed = base[: 50 - (len(str(suffix)) + 1)]
        code = f"{trimmed}_{suffix}"
        suffix += 1
    return code


org_defs = [
    {"code": "BONELA", "name": "BONELA"},
    {"code": "BONEPWA", "name": "BONEPWA"},
    {"code": "MAKGABANE", "name": "MAKGABANE"},
    {"code": "MBGE", "name": "MBGE"},
    {"code": "TEBELOPELE", "name": "TEBELOPELE"},
]

indicator_map = {
    "BONELA": [
        "Number of sub recipients mentored per month",
        "Number of sub-recipients submitting quality reports per months",
        "Total Number of Key and Vulnerable Populations Reached with HIV TESTING Messages",
        "Number of people reached with stigma reduction messages",
        "Number of people referred for Hiv testing",
        "Number of people referred for PrEP",
        "Number of individuals screened for GBV",
        "Number of people screened for STIs",
        "Number of condoms distributed to KVPs",
        "Number of braided condoms distributed to PWDs",
        "Number of promotions on braille labelled condoms held",
        "Number of lubricants distributed",
        "Number of people sensitised on basic human rights and HIV",
        "Number of community led monitoring conducted for quality of service and human rights",
        "Number of advocacy activities conducted per quarter",
        "Number of media platforms used per quarter",
        "Number of target specific demand creation activities conducted",
        "Number of media engagements conducted",
        "Number of stigma reduction campaigns conducted during the project",
    ],
    "BONEPWA": [
        "Number of sub recipients mentored per month (Number of sub-recipients visited)",
        "Number of sub-recipients submitting quality reports per months",
        "Number of PLWH reached with HIV TESTING Messages",
        "Number of people reached with stigma reduction messages",
        "Number of PLWHs provided with treatment literacy",
        "Number of PLWH who tested positive for TB and are on treatment",
        "Number of people sensitised on basic human rights and HIV",
        "Number of individuals screened for GBV",
        "Number of Male Condoms distributed",
        "Number of Lubricants distributed to PLHIV",
        "Number of people screened for STIs",
        "Number of Community led monitoring conducted for quality of service and human rights",
        "Number of advocacy activities conducted per quarter",
        "Number of media platforms used per quarter",
        "Number of media engagements conducted",
        "Number of target specific demand creation activities conducted",
        "Number of stigma reduction campaigns conducted during the project",
    ],
    "MAKGABANE": [
        "Number of sub recipients mentored per month",
        "Number of sub-recipients submitting quality reports per month",
        "Total number of people reached with NCD prevention and Control messages",
        "Number of people engaged with NCD prevention and control messages through social media",
        "Number of advocacy activities conducted per quarter",
        "Number of media platforms used per quarter",
        "Number of target specific demand creation activities conducted",
        "Number of media engagements conducted",
        "Number of people reached with self-breast cancer examination education",
        "Number of people reached with prostate cancer education",
        "Number of people reached with cervical cancer education",
        "Number of people screened for NCDs behavioural risk factors (Tobacco use)",
        "Number of people screened for NCDs behavioural risk factors (Alcohol use)",
        "Number of people screened for NCDs risk factors",
        "Number of people screened for breast cancer",
        "Number of people screened for mental health",
        "Number of people receiving counselling",
        "Number of counselling sessions conducted",
        "Number of people utilizing community based physical activity clubs",
        "Number of functional cancer support groups",
        "Number of functional tobacco cessation and alcohol abuse support group",
        "Number of people who attended World Diabetes Day activities",
        "Number of people who attended the Breast Cancer Month activities",
        "Number of people who attended cervical cancer awareness activities",
        "Number of people who attended Mental health Day activities",
        "Number of people who attended Mo-Vember Day activities",
    ],
    "MBGE": [
        "Number of sub recipients mentored per month",
        "Number of sub-recipients submitting quality reports per months",
        "Total Number of Key and Vulnerable Populations Reached with HIV TESTING Messages",
        "Total Number of Key and Vulnerable Populations Reached with PREP Messages",
        "Number of people reached with stigma reduction messages",
        "Number of people tested for HIV",
        "Number of people who tested positive for HIV",
        "Number of people referred for PrEP",
        "Number of individuals screened for GBV",
        "Number of people screened for STIs",
        "Number of condoms distributed",
        "Total number of lubricants distributed",
        "Number of people sensitised on basic human rights and HIV",
        "Number of advocacy activities conducted per quarter",
        "Number of media platforms used per quarter",
        "Number of target specific demand creation activities conducted",
        "Number of media engagements conducted",
        "Number of stigma reduction campaigns conducted during the project",
        "Number of community led monitoring conducted for quality of service and human rights",
    ],
    "TEBELOPELE": [
        "Number of sub recipients mentored per month",
        "Number of CSOs trained and equipped to provide comprehensive psychosocial and practical support",
        "Number of sub-recipients submitting quality reports per months",
        "Total Number of people Reached with HIV TESTING Messages",
        "Number of people reached with stigma reduction messages",
        "Number of people tested for HIV",
        "Number of people who tested positive for HIV",
        "Number of people referred for PrEP",
        "Number of AYP provided with family planning services",
        "Number of individuals screened for GBV",
        "Number of people screened for STIs",
        "Number of condoms distributed to AYPS",
        "Number of lubricants distributed",
        "Number of people sensitised on basic human rights and HIV",
        "Number of community led monitoring conducted for quality of service and human rights",
        "Number of advocacy activities conducted per quarter",
        "Number of media platforms used per quarter",
        "Number of target specific demand creation activities conducted",
        "Number of media engagements conducted",
        "Number of stigma reduction campaigns conducted during the project",
    ],
}

event_indicator_defs = [
    {"code": "EVT_COMM", "name": "Number of commemorations conducted"},
    {"code": "EVT_ACTIVITIES", "name": "Number of activities conducted"},
    {"code": "EVT_TRAINING", "name": "Number of trainings conducted"},
    {"code": "EVT_MEETINGS", "name": "Number of meetings conducted"},
    {"code": "EVT_OUTREACH", "name": "Number of outreach activities conducted"},
    {"code": "EVT_WORKSHOPS", "name": "Number of workshops conducted"},
]


with transaction.atomic():
    org_objs = {}
    for org in org_defs:
        obj, created = Organization.objects.get_or_create(
            code=org["code"],
            defaults={
                "name": org["name"],
                "type": "partner",
                "is_active": True,
            },
        )
        if not created and obj.name != org["name"]:
            obj.name = org["name"]
            obj.type = "partner"
            obj.save(update_fields=["name", "type"])
        org_objs[org["code"]] = obj

    created_indicators = 0
    linked_pairs = 0
    created_assessments = 0
    linked_assessments = 0
    created_project_indicators = 0
    created_tasks = 0

    for org_code, names in indicator_map.items():
        org = org_objs.get(org_code)
        if not org:
            continue
        unique_names = list(dict.fromkeys(names))
        for name in unique_names:
            indicator = Indicator.objects.filter(name=name).first()
            if not indicator:
                indicator = Indicator.objects.create(
                    name=name,
                    code=make_code(name),
                    type="number",
                    category="health",
                    aggregation_method="sum",
                    is_active=True,
                )
                created_indicators += 1
            indicator.organizations.add(org)
            linked_pairs += 1

    # Event indicators shared across organizations
    event_indicators = []
    for defn in event_indicator_defs:
        indicator, created = Indicator.objects.get_or_create(
            code=defn["code"],
            defaults={
                "name": defn["name"],
                "type": "number",
                "category": "social",
                "aggregation_method": "sum",
                "is_active": True,
            },
        )
        if not created and indicator.name != defn["name"]:
            indicator.name = defn["name"]
            indicator.save(update_fields=["name"])
        if created:
            created_indicators += 1
        event_indicators.append(indicator)

    for org in org_objs.values():
        for indicator in event_indicators:
            indicator.organizations.add(org)
            linked_pairs += 1

    # Create assessments per organization and link indicators
    for org in org_objs.values():
        assessment, created = Assessment.objects.get_or_create(
            name=f"{org.code} Assessment",
            defaults={
                "description": f"{org.name} indicators assessment",
                "is_active": True,
            },
        )
        if created:
            created_assessments += 1
        assessment.organizations.add(org)

        indicators = Indicator.objects.filter(organizations=org).distinct().order_by("name")
        order = 1
        for indicator in indicators:
            ai, created_ai = AssessmentIndicator.objects.get_or_create(
                assessment=assessment,
                indicator=indicator,
                defaults={"order": order, "is_required": True},
            )
            if created_ai:
                linked_assessments += 1
            order += 1

    # Assign indicators to projects and create tasks
    all_orgs = list(org_objs.values())
    for project in Project.objects.all():
        project_orgs = list(project.organizations.all())
        scoped_orgs = project_orgs if project_orgs else all_orgs
        indicators = (
            Indicator.objects.filter(organizations__in=scoped_orgs)
            .distinct()
            .order_by("name")
        )
        for indicator in indicators:
            _, created_pi = ProjectIndicator.objects.get_or_create(
                project=project,
                indicator=indicator,
            )
            if created_pi:
                created_project_indicators += 1
            _, created_task = Task.objects.get_or_create(
                project=project,
                name=indicator.name,
                defaults={
                    "description": indicator.description,
                    "status": "pending",
                    "priority": "medium",
                },
            )
            if created_task:
                created_tasks += 1

print(f"Organizations ensured: {len(org_defs)}")
print(f"Indicators created: {created_indicators}")
print(f"Organization-indicator links added: {linked_pairs}")
print(f"Assessments created: {created_assessments}")
print(f"Assessment-indicator links added: {linked_assessments}")
print(f"Project indicators added: {created_project_indicators}")
print(f"Tasks ensured: {created_tasks}")
