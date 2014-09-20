from django.test import TestCase


class ApiAccessTest(TestCase):
    def test_a_user_can_search_crunchbase(self):
        response = self.client.get('/search')
        self.assertEqual(response.status_code, 200)