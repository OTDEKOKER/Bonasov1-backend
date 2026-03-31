from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from analysis.models import Report
from indicators.models import Indicator
from organizations.models import Organization

User = get_user_model()


class DashboardPreferencesApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name='Dashboard Org',
            code='DASH-ORG',
            type='ngo',
        )
        cls.user = User.objects.create_user(
            username='dashboard-user',
            email='dashboard@example.com',
            password='StrongPassword123!',
            role='officer',
            organization=cls.organization,
        )
        cls.visible_indicator = Indicator.objects.create(
            name='People tested for HIV',
            code='HTS_TST',
            category='hiv_prevention',
            is_active=True,
        )
        cls.visible_indicator.organizations.add(cls.organization)
        cls.global_indicator = Indicator.objects.create(
            name='HIV positive',
            code='HTS_POS',
            category='hiv_prevention',
            is_active=True,
        )
        cls.hidden_indicator = Indicator.objects.create(
            name='Other Org Only',
            code='OTHER_1',
            category='gbv',
            is_active=True,
        )
        cls.other_organization = Organization.objects.create(
            name='Other Org',
            code='OTHER-ORG',
            type='ngo',
        )
        cls.hidden_indicator.organizations.add(cls.other_organization)

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_get_preferences_creates_default_report(self):
        response = self.client.get('/api/analysis/dashboard/preferences/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['preferences']['selected_indicator_ids'], [])
        self.assertEqual(body['preferences']['card_order'], [])
        self.assertEqual(body['preferences']['hidden_sections'], [])
        self.assertEqual(body['preferences']['layout'], {})
        self.assertCountEqual(
            [entry['id'] for entry in body['available_indicators']],
            [self.visible_indicator.id, self.global_indicator.id],
        )
        self.assertTrue(
            Report.objects.filter(
                id=body['report_id'],
                created_by=self.user,
                report_type='dashboard',
            ).exists()
        )

    def test_put_preferences_saves_selected_indicator_ids(self):
        response = self.client.put(
            '/api/analysis/dashboard/preferences/',
            {
                'selected_indicator_ids': [self.global_indicator.id, self.visible_indicator.id],
                'card_order': ['summary', 'pathways'],
                'hidden_sections': ['targets'],
                'layout': {'pathways': {'columns': 2}},
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(
            body['preferences']['selected_indicator_ids'],
            [self.global_indicator.id, self.visible_indicator.id],
        )
        report = Report.objects.get(id=body['report_id'])
        self.assertEqual(
            report.parameters['preferences']['selected_indicator_ids'],
            [self.global_indicator.id, self.visible_indicator.id],
        )
        self.assertEqual(report.parameters['preferences']['card_order'], ['summary', 'pathways'])

    def test_put_preferences_rejects_unknown_or_inactive_indicator_ids(self):
        self.hidden_indicator.is_active = False
        self.hidden_indicator.save(update_fields=['is_active'])

        response = self.client.put(
            '/api/analysis/dashboard/preferences/',
            {
                'selected_indicator_ids': [self.hidden_indicator.id],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('selected_indicator_ids', response.json())
