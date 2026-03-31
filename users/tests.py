from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework import status
from rest_framework.test import APITestCase

from organizations.models import Organization

User = get_user_model()


class TokenLoginApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='login-user',
            email='login@example.com',
            password='StrongPassword123!',
            role='admin',
            is_staff=True,
        )

    def test_request_token_accepts_email_identifier(self):
        response = self.client.post(
            '/api/users/request-token/',
            {
                'username': 'login@example.com',
                'password': 'StrongPassword123!',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertIn('access', body)
        self.assertIn('refresh', body)


class UserPermissionsApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name='Test Organization',
            code='TEST-ORG',
            type='ngo',
        )
        cls.admin = User.objects.create_user(
            username='admin-user',
            email='admin@example.com',
            password='StrongPassword123!',
            role='admin',
            is_staff=True,
        )
        cls.officer = User.objects.create_user(
            username='officer-user',
            email='officer@example.com',
            password='StrongPassword123!',
            role='officer',
            organization=cls.organization,
        )
        cls.view_org_permission = Permission.objects.get(
            content_type__app_label='organizations',
            codename='view_organization',
        )
        cls.change_org_permission = Permission.objects.get(
            content_type__app_label='organizations',
            codename='change_organization',
        )

    def test_admin_can_list_assignable_permissions(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get('/api/users/permissions/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            {
                'id': 'organizations.view_organization',
                'app_label': 'organizations',
                'codename': 'view_organization',
                'name': self.view_org_permission.name,
            },
            response.json(),
        )
        self.assertFalse(any(entry['app_label'] == 'auth' for entry in response.json()))

    def test_non_admin_cannot_list_assignable_permissions(self):
        self.client.force_authenticate(user=self.officer)

        response = self.client.get('/api/users/permissions/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_detail_includes_permission_identifiers(self):
        self.officer.user_permissions.add(self.view_org_permission)
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(f'/api/users/{self.officer.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['permissions'], ['organizations.view_organization'])

    def test_admin_can_create_user_with_permissions(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            '/api/users/',
            {
                'username': 'new-user',
                'email': 'new-user@example.com',
                'first_name': 'New',
                'last_name': 'User',
                'role': 'officer',
                'organization': self.organization.id,
                'password': 'StrongPassword123!',
                'password_confirm': 'StrongPassword123!',
                'permissions': [
                    'organizations.view_organization',
                    'organizations.change_organization',
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(username='new-user')
        self.assertCountEqual(
            [
                f'{permission.content_type.app_label}.{permission.codename}'
                for permission in created_user.user_permissions.select_related('content_type')
            ],
            [
                'organizations.view_organization',
                'organizations.change_organization',
            ],
        )

    def test_admin_can_update_user_permissions(self):
        self.officer.user_permissions.add(self.view_org_permission)
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f'/api/users/{self.officer.id}/',
            {
                'permissions': ['organizations.change_organization'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.officer.refresh_from_db()
        self.assertEqual(
            [
                f'{permission.content_type.app_label}.{permission.codename}'
                for permission in self.officer.user_permissions.select_related('content_type')
            ],
            ['organizations.change_organization'],
        )

    def test_non_admin_cannot_update_permissions(self):
        self.client.force_authenticate(user=self.officer)

        response = self.client.patch(
            f'/api/users/{self.officer.id}/',
            {
                'permissions': ['organizations.view_organization'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()['permissions'],
            ['Only admins can update this field.'],
        )
