from django.core import urlresolvers
from django.test import TestCase


class ApiAccessTest(TestCase):
    def test_a_user_can_search_crunchbase(self):
        from django.conf import settings
        response = self.client.get(urlresolvers.reverse('crunchbase:search'))
        self.assertEqual(response.status_code, 200)