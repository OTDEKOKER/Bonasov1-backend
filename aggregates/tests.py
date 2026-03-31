from datetime import date

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from aggregates.models import Aggregate, AggregateChangeLog
from indicators.models import Indicator
from organizations.models import Organization
from projects.models import Project

User = get_user_model()


class AggregateApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name='Aggregate Org',
            code='AGG-ORG',
            type='ngo',
        )
        cls.admin = User.objects.create_user(
            username='aggregate-admin',
            email='aggregate-admin@example.com',
            password='StrongPassword123!',
            role='admin',
            is_staff=True,
        )
        cls.officer = User.objects.create_user(
            username='aggregate-officer',
            email='aggregate-officer@example.com',
            password='StrongPassword123!',
            role='officer',
            organization=cls.organization,
        )
        cls.indicator = Indicator.objects.create(
            name='Aggregate indicator',
            code='AGG_001',
            category='hiv_prevention',
            type='number',
            is_active=True,
        )
        cls.project = Project.objects.create(
            name='Aggregate Project',
            code='AGG-PROJ',
            status='active',
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            created_by=cls.admin,
        )
        cls.aggregate = Aggregate.objects.create(
            indicator=cls.indicator,
            project=cls.project,
            organization=cls.organization,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 3, 31),
            value={'total': 12},
            notes='Initial aggregate',
            created_by=cls.officer,
        )
        cls.history_entry = AggregateChangeLog.objects.create(
            aggregate=cls.aggregate,
            action=AggregateChangeLog.ACTION_SUBMITTED,
            changed_by=cls.officer,
            comment='Submitted for review',
            changes={'status': {'from': None, 'to': Aggregate.STATUS_PENDING}},
        )

    def setUp(self):
        self.client.force_authenticate(user=self.admin)

    def test_list_response_omits_history_entries(self):
        response = self.client.get('/api/aggregates/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['count'], 1)
        self.assertNotIn('history_entries', body['results'][0])
        self.assertEqual(body['results'][0]['created_by_name'], self.officer.username)

    def test_detail_response_includes_history_entries(self):
        response = self.client.get(f'/api/aggregates/{self.aggregate.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('history_entries', body)
        self.assertEqual(len(body['history_entries']), 1)
        self.assertEqual(body['history_entries'][0]['changed_by_name'], self.officer.username)
