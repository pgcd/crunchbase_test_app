from django.core import urlresolvers
from django.core.cache import cache
from django.test import TestCase
from requests import Response
from crunchbase.views import CrunchbaseQuery, CrunchbaseEndpoint
from django_webtest import WebTest
import mock


class FrontendAccessTest(WebTest):
    def test_a_user_can_search_crunchbase(self):
        response = self.app.get(urlresolvers.reverse('crunchbase:search'))
        self.assertEqual(response.status_code, 200)
        # the main page should return a link to the two main querysets
        companies_search_url = urlresolvers.reverse('crunchbase:search', args=('companies',))
        self.assertTrue(response.html.find('a', text='Companies', href=companies_search_url))
        products_search_url = urlresolvers.reverse('crunchbase:search', args=('products',))
        self.assertTrue(response.html.find('a', text='Products', href=products_search_url))

    def test_the_main_search_page_shows_first_ten_results_of_both(self):
        response = self.app.get(urlresolvers.reverse('crunchbase:search'))
        self.assertIn('companies_search_results', response.context)
        self.assertEqual(len(response.context['companies_search_results']), 10)

    def test_results_in_main_page_show_description_and_logo(self):
        # HTML-intensive test, might have to be refactored later
        response = self.app.get(urlresolvers.reverse('crunchbase:search'))
        companies_list = response.html.find('table', id="companies-list")
        self.assertTrue(companies_list)
        self.assertEqual(len(companies_list.find_all('tr', class_='company-info')), 10)
        # we're gonna check only the first one
        company_row_cells = companies_list.find('tr', class_='company-info').find_all('td')
        self.assertEqual(len(company_row_cells), 3)  # Name, description and logo
        self.assertEqual(company_row_cells[0].string, response.context['companies_search_results'][0]['name'])
        # The following requires changing the output to also include description and logo
        self.assertEqual(company_row_cells[1].string, response.context['companies_search_results'][0]['description'])


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
        response = self.bcq.companies.list(raw=True)
        self.assertIsInstance(response, Response)
        # The two relevant bits here are the status code (for auth) and the response length (for the actual data)
        self.assertEqual(response.status_code, 200)
        json = response.json()
        self.assertGreaterEqual(len(json['data']['items']), 10)  # Min page length from requirements


class EndpointTest(TestCase):
    # The actual CrunchBase API does not seem to allow setting a page size, so we're gonna have to work around that
    # by implementing a sub-pagination in our model, with some related stuff
    def setUp(self):
        self.ep = CrunchbaseEndpoint(CrunchbaseQuery.ENDPOINTS['companies'])

    def test_list_returns_data(self):
        data = self.ep.list()
        self.assertIsInstance(data, dict)

    def test_crunchquery_list_can_be_limited(self):
        json = self.ep.list()
        self.assertEqual(len(json['items']), 10)

    def test_list_items_are_cached(self):
        actual_return = self.ep.list(raw=True)
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            cache.clear()
            req.get.return_value = actual_return
            self.ep.list()
            self.assertEqual(req.get.call_count, 1)
            # If we call it a second time, we expect requests not to be called again
            self.ep.list()
            self.assertEqual(req.get.call_count, 1)

    def test_list_items_include_extra_information(self):
        # We should be able to leverage the previously set cache; in any case, we're going to load only the first 2 items here
        data = self.ep.list(per_page=2)