from django.core import urlresolvers
from django.core.cache import cache
from django.test import TestCase
from requests import Response
from unittest import skip
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
        self.assertEqual(company_row_cells[1].string,
                         response.context['companies_search_results'][0]['properties__short_description'])
        self.assertEqual(company_row_cells[2].find('img').attrs['src'],
                         response.context['companies_search_results'][0]['primary_image'])


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
        self.sample_list_data = {
            'items': [{'created_at': 1411368793,
                       'name': 'Web Tools Weekly',
                       'path': 'organization/web-tools-weekly',
                       'type': 'Organization',
                       'updated_at': 1411369054},
                      {'created_at': 1411368747,
                       'name': 'Corpora',
                       'path': 'organization/corpora',
                       'type': 'Organization',
                       'updated_at': 1411368824}],
            'paging': {'current_page': 1,
                       'items_per_page': 1000,
                       'next_page_url': 'http://api.crunchbase.com/v/2/organizations?page=2',
                       'number_of_pages': 287,
                       'prev_page_url': None,
                       'sort_order': 'created_at DESC',
                       'total_items': 286559}}
        self.sample_detail_data = {
            'metadata': {
                'api_path_prefix': u'http://api.crunchbase.com/v/2/',
                'image_path_prefix': u'http://images.crunchbase.com/',
                'version': 2,
                'www_path_prefix': u'http://www.crunchbase.com/'},
            'data': {
                'properties': {'closed_on': None,
                               'closed_on_day': None,
                               'closed_on_month': None,
                               'closed_on_trust_code': 0,
                               'closed_on_year': None,
                               'created_at': 1411368793,
                               'description': 'Each issue features a brief tip or tutorial, followed by a '
                                              'weekly round-up of various apps, scripts, plugins, '
                                              'and other resources to help front-end developers solve '
                                              'problems and be more productive.\n',
                               'homepage_url': 'http://webtoolsweekly.com/',
                               'is_closed': False,
                               'name': 'Web Tools Weekly',
                               'num_employees_max': None,
                               'num_employees_min': None,
                               'num_employees_range': None,
                               'number_of_investments': 0,
                               'permalink': 'web-tools-weekly',
                               'primary_role': 'company',
                               'role_company': True,
                               'secondary_role_for_profit': True,
                               'short_description': 'A weekly newsletter for front-end developers and web '
                                                    'designers.',
                               'total_funding_usd': 0,
                               'updated_at': 1411369054},
                'relationships': {
                    'categories': {'items': [{'created_at': 1397980727,
                                              'name': 'Web Development',
                                              'path': 'category/web '
                                                      'development/292d82c553819717827f3122ee792e71',
                                              'type': 'Category',
                                              'updated_at': 1411368852,
                                              'uuid': '292d82c553819717827f3122ee792e71'}],
                                   'paging': {
                                       'first_page_url': 'http://api.crunchbase.com/v/2/organization/web-tools-weekly/categories',
                                       'sort_order': 'created_at DESC',
                                       'total_items': 1}},
                    'images': {'items': [{'created_at': 1411369054,
                                          'path': 'image/upload/v1411369051/al2ub9nvgqtqjru4ncvl.png',
                                          'title': None,
                                          'type': 'ImageAsset',
                                          'updated_at': 1411369054}],
                               'paging': {
                                   'first_page_url': 'http://api.crunchbase.com/v/2/organization/web-tools-weekly/images',
                                   'sort_order': 'created_at DESC',
                                   'total_items': 1}},
                    'primary_image': {'items': [{'created_at': 1411368794,
                                                 'path': 'image/upload/v1411368785/k6fnzdjqhambbqsaxp2y.jpg',
                                                 'title': None,
                                                 'type': 'ImageAsset',
                                                 'updated_at': 1411368794}],
                                      'paging': {
                                          'first_page_url':
                                              'http://api.crunchbase.com/v/2/organization/web-tools-weekly/primary_image',
                                          'sort_order': 'created_at DESC',
                                          'total_items': 1}},
                    'websites': {'items': [{'created_at': 1411368827,
                                            'title': 'twitter',
                                            'type': 'WebPresence',
                                            'updated_at': 1411368828,
                                            'url': 'https://twitter.com/WebToolsWeekly'},
                                           {'created_at': 1411368794,
                                            'title': 'homepage',
                                            'type': 'WebPresence',
                                            'updated_at': 1411368794,
                                            'url': 'http://webtoolsweekly.com/'}],
                                 'paging': {
                                     'first_page_url': 'http://api.crunchbase.com/v/2/organization/web-tools-weekly/websites',
                                     'sort_order': 'created_at DESC',
                                     'total_items': 2}}},
                'type': 'Organization',
                'uuid': 'edcf9d3fafe5de0fd10181f6a8a9b7f6'}
        }

    def test_list_returns_data(self):
        data = self.ep.list()
        self.assertIsInstance(data, dict)

    def test_crunchquery_list_can_be_limited(self):
        json = self.ep.list(per_page=10)['data']
        self.assertEqual(len(json['items']), 10)

    @skip("To avoid clearing the cache during the tests")
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

    def test_detail_returns_data(self):
        # The value should be cached, hopefully - Ideally we would mock this up but...
        path = self.sample_list_data['items'][0]['path']
        detail_response = self.ep.detail(path, raw=True)
        self.assertEqual(detail_response.status_code, 200)
        detail_data = self.ep.detail(path)['data']
        # At the moment, the only data we're interested in is the description
        self.assertIn('short_description', detail_data['properties'])

    @skip("To avoid removing the cached values")
    def test_detail_data_is_cached(self):
        # It should be "are cached", yes.
        path = self.sample_list_data['data']['items'][0]['path']
        actual_return = self.ep.detail(path, raw=True)
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            cache.delete(path)
            req.get.return_value = actual_return
            self.ep.detail(path)
            self.assertEqual(req.get.call_count, 1)
            self.ep.detail(path)
            self.assertEqual(req.get.call_count, 1)

    def test_list_items_can_include_extra_information(self):
        # We should be able to leverage the previously set cache; in any case, we're going to load only the first 2 items here
        data = self.sample_list_data
        # A better solution would be to use something like a queryset, so that we could do list().values('something','etc')
        # but, given the time constraints we'll go with a dict of extra values
        data = self.ep.list(per_page=2, fetch_values=('properties__short_description',))['data']
        item = data['items'][0]
        self.assertIn('properties__short_description', item)
        # Of course, we expect the actual description to match that in the details page of the item, so:
        detail = self.ep.detail(item['path'])
        self.assertEqual(detail['data']['properties']['short_description'], item['properties__short_description'])

    def test_fetch_values_returns_correct_image_data(self):
        # Testing images with the live Crunchbase API proved basically useless, so I've decided to go with fixtures for this
        fetched_values = self.ep.fetch_item_values(self.sample_list_data['items'][0]['path'], ('primary_image', ))
        self.assertEqual(
            self.sample_detail_data['metadata']['image_path_prefix'] +
            self.sample_detail_data['data']['relationships']['primary_image']['items'][0]['path'],
            fetched_values['primary_image'])
