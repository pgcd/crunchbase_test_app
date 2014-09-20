from django.core import urlresolvers
from django.test import TestCase


class ApiAccessTest(TestCase):
    def test_a_user_can_search_crunchbase(self):
        response = self.client.get(urlresolvers.reverse('crunchbase:search'))
        self.assertEqual(response.status_code, 200)
        # the main page should return a link to the two main querysets
        companies_search_url = urlresolvers.reverse('crunchbase:search', args=('companies',))
        self.assertContains(response, '<a href="%s">Companies</a>' % companies_search_url)
        products_search_url = urlresolvers.reverse('crunchbase:search', args=('products',))
        self.assertContains(response, '<a href="%s">Products</a>' % products_search_url)