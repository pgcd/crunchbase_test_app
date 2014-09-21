from django.core import urlresolvers
from django.test import TestCase
from requests import Response
from unittest import skip
from crunchbase.views import CrunchbaseQuery


class FrontendAccessTest(TestCase):
    def test_a_user_can_search_crunchbase(self):
        response = self.client.get(urlresolvers.reverse('crunchbase:search'))
        self.assertEqual(response.status_code, 200)
        # the main page should return a link to the two main querysets
        companies_search_url = urlresolvers.reverse('crunchbase:search', args=('companies',))
        self.assertContains(response, '<a href="%s">Companies</a>' % companies_search_url)
        products_search_url = urlresolvers.reverse('crunchbase:search', args=('products',))
        self.assertContains(response, '<a href="%s">Products</a>' % products_search_url)

    def test_the_main_search_page_shows_first_ten_results_of_both(self):
        response = self.client.get(urlresolvers.reverse('crunchbase:search'))
        self.assertIn('companies_search_results', response.context)
        self.assertEqual(len(response.context['companies_search_results']), 10)


class ApiQueryTest(TestCase):
    def setUp(self):
        self.bcq = CrunchbaseQuery()
        super(ApiQueryTest, self).setUp()

    def test_crunchquery_can_list_endpoints(self):
        endpoints = self.bcq.list_endpoint_uris()
        # I'd like the endpoints to be returned in a dict format: {verbose_name: uri}
        self.assertIsInstance(endpoints, dict)
        # For this project, we only need the Companies and the Products endpoints
        self.assertIn('companies', endpoints)
        self.assertIn('products', endpoints)

    def test_all_endpoints_queries_are_aliased_as_attributes(self):
        # In real life, this might possibly lead to shadowing but that's not a concern in our scenario, since we're only
        # going to have companies and products
        self.assertTrue(all([hasattr(self.bcq, x) for x in self.bcq.list_endpoint_uris()]))

    def test_crunchquery_can_connect_to_endpoints(self):
        # a true API would require several verbs; initially, though, we need to be able to list stuff.
        response = self.bcq.companies.list()
        self.assertIsInstance(response, Response)
        # The two relevant bits here are the status code (for auth) and the response length (for the actual data)
        self.assertEqual(response.status_code, 200)
        json = response.json()
        self.assertGreaterEqual(len(json['data']['items']), 10)  # Min page length from requirements