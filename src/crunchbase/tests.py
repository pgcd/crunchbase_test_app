from django.conf import settings
from django.core import urlresolvers
from django.core.cache import cache
from django.http import Http404
from django.test import TestCase
from requests import Response
import requests
from unittest import skip
from crunchbase.views import CrunchbaseQuery, CrunchbaseEndpoint, CrunchbaseQueryset
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

    def test_the_main_search_page_allows_searching_within_subsets(self):
        response = self.app.get(urlresolvers.reverse('crunchbase:search'))
        self.assertTrue(response.forms['form-companies'])
        # most basic approach - if we enter the name of one of the results in the form we should find it in the results
        company = response.context['companies_search_results'][0]
        response.forms['form-companies']['query'] = company['name']
        response = response.forms['form-companies'].submit()
        self.assertIn(company, response.context['object_list'])

    def test_results_in_main_page_show_description_and_logo(self):
        # HTML-intensive test, might have to be refactored later
        response = self.app.get(urlresolvers.reverse('crunchbase:search'))
        companies_list = response.html.find('table', id="companies-list")
        self.assertTrue(companies_list)
        self.assertEqual(len(companies_list.find_all('tr', class_='companies-info')), 10)
        # we're gonna check only the first one
        company_row_cells = companies_list.find('tr', class_='companies-info').find_all('td')
        self.assertEqual(len(company_row_cells), 3)  # Name, description and logo
        self.assertEqual(company_row_cells[0].string, response.context['companies_search_results'][0]['name'])
        # The following requires changing the output to also include description and logo
        self.assertEqual(company_row_cells[1].string,
                         response.context['companies_search_results'][0]['properties__short_description'])
        self.assertEqual(company_row_cells[2].find('img').attrs['src'],
                         response.context['companies_search_results'][0]['primary_image'])
        # And now the products
        products_list = response.html.find('table', id="products-list")
        self.assertTrue(products_list)
        self.assertEqual(len(products_list.find_all('tr', class_='products-info')), 10)
        # Same checks as for the companies
        product_row_cells = products_list.find('tr', class_='products-info').find_all('td')
        self.assertEqual(len(product_row_cells), 3)
        self.assertEqual(product_row_cells[0].string, response.context['products_search_results'][0]['name'])
        self.assertEqual(product_row_cells[1].string,
                         response.context['products_search_results'][0]['properties__short_description'])
        self.assertEqual(product_row_cells[2].find('img').attrs['src'],
                         response.context['products_search_results'][0]['primary_image'])

    def test_type_specific_pages_have_specific_resultset(self):
        # While the homepage injects the resultset into the context data, the two type-specific pages need to use pagination,
        # so we're gonna try to leverage at least some of Django's functionality for it
        response = self.app.get(urlresolvers.reverse('crunchbase:search', args=('companies',)), status=200)

        # We expect the context data to hold the companies in the object_list key, and that the view does not injects data
        self.assertNotIn('products_search_results', response.context)
        self.assertNotIn('companies_search_results', response.context)
        self.assertEqual(len(response.context['search_results']), 10)
        self.assertEqual(response.context['search_results'][0]['type'], 'Organization')

        # sanity check: the same url with an unsupported subset should return a 404
        self.app.get(urlresolvers.reverse('crunchbase:search') + '/people', status=404)

    def test_type_specific_results_can_be_paginated(self):
        response = self.app.get(urlresolvers.reverse('crunchbase:search', args=('companies',)), status=200)
        self.assertTrue(response.context['is_paginated'])
        # In this case, we expect to be able to paginate forwards, not back - and this is where we're forced to implement
        # our own paginator class
        self.assertTrue(response.context['page_obj'].has_next())
        page_1_content = response.context['object_list']
        # if we retrieve the next page, it should have a different set of objects
        nxt = response.context['page_obj'].next_page_number()
        response = self.app.get(urlresolvers.reverse('crunchbase:search', args=('companies',)), params={'page': nxt}, status=200)
        page_2_content = response.context['object_list']
        # We should probably test for null-intersection, actually, but I guess it's ok to just see that it's not the same page
        self.assertNotEqual(page_1_content[0]['path'], page_2_content[0]['path'])
        # the pages should also have actual HTML to change page
        response = response.click("prev")
        self.assertItemsEqual(page_1_content, response.context['object_list'])
        response = response.click("next")
        self.assertItemsEqual(page_2_content, response.context['object_list'])

    def test_detail_page_works_for_companies(self):
        # The detail page should be accessible from the list index
        response = self.app.get(urlresolvers.reverse('crunchbase:search', args=('companies',)), status=200)
        item = response.context['object_list'][0]
        response = response.click(item['name'])  # The names should be linked
        self.assertEqual(response.status_code, 200)
        self.assertIn('object', response.context)
        # A quick check for the basic properties
        self.assertIn('properties', response.context['object'])
        # We also need to have the metadata available for images and crunchbase urls.
        self.assertIn('metadata', response.context)


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


class CBSampleDataMixin(object):
    sample_detail_data = {
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
    sample_list_data = {
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
    sample_list_json = {'metadata': {}, 'data': sample_list_data}


class EndpointTest(TestCase, CBSampleDataMixin):
    # The actual CrunchBase API does not seem to allow setting a page size, so we're gonna have to work around that
    # by implementing a sub-pagination in our model, with some related stuff
    def setUp(self):
        self.ep = CrunchbaseEndpoint(CrunchbaseQuery.ENDPOINTS['companies'])

    def test_list_returns_data(self):
        data = self.ep.list()
        self.assertIsInstance(data, dict)

    def test_crunchquery_list_can_be_limited(self):
        json = self.ep.list(per_page=10)['data']
        self.assertEqual(len(json['items']), 10)

    def test_crunchquery_list_can_be_paginated(self):
        # Since the default page size is 10, we're getting the results for two pages here
        full_list = self.ep.list(per_page=20)
        self.assertEqual(full_list['data']['paging']['per_page'], 20)
        self.assertEqual(full_list['data']['paging']['page'], 0)
        second_page = self.ep.list(page=1)  # page is 0-based, so this is the second page
        self.assertSequenceEqual(second_page['data']['items'], full_list['data']['items'][10:])
        self.assertEqual(second_page['data']['paging']['per_page'], 10)
        self.assertEqual(second_page['data']['paging']['page'], 1)

    def test_crunchquery_list_retrieves_new_pages_when_required(self):
        # If the page number * per_page is more than what a CB page returns, we should try to get the proper one
        far_page = self.ep.list(page=101)  # Second page of CB
        self.assertEqual(len(far_page['data']['items']), 10)  # For now I'll settle for checking the metadata, rather than the val
        self.assertEqual(far_page['data']['paging']['per_page'], 10)
        self.assertEqual(far_page['data']['paging']['page'], 101)
        # If we try to fetch a non-existing page, we should raise a 404
        self.assertRaises(Http404, lambda: self.ep.list(page=100000, per_page=100000))

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

    def test_list_data_can_be_sliced(self):
        self.assertTrue(hasattr(self.ep, 'datastore'))
        # The idea is that the datastore will allow to retrieve all the metadata and that it will work basically as a queryset
        # for Django purposes;
        # This means that it must have some sort of meta attribute to store all the metadata from the queries (single and list)
        # and that it must support slicing, length and item retrieval.
        self.assertIsInstance(self.ep.datastore, CrunchbaseQueryset)
        # To make thing


class CBQuerysetTest(TestCase, CBSampleDataMixin):
    @classmethod
    def setUpClass(cls):
        super(CBQuerysetTest, cls).setUpClass()
        cls.cbqs = CrunchbaseQueryset(cls.sample_list_json)
        cls.dataset_uri = CrunchbaseEndpoint.BASE_URI + 'organizations'
        cls.page1 = cache.get('test_page1')
        if cls.page1 is None:
            cls.page1 = requests.get(cls.dataset_uri, params={'user_key': settings.CRUNCHBASE_USER_KEY})
            cache.set('test_page1', cls.page1, timeout=None)
        cls.page2 = cache.get('test_page2')
        if cls.page2 is None:
            cls.page2 = requests.get(cls.dataset_uri, params={'user_key': settings.CRUNCHBASE_USER_KEY, 'page': 2})
            cache.set('test_page2', cls.page2, timeout=None)

    def test_length_is_the_total_number_of_items_from_cb_api(self):
        self.assertTrue(len(self.cbqs))
        self.assertEqual(len(self.cbqs), int(self.sample_list_data['paging']['total_items']))

    def test_items_can_be_retrieved_when_in_current_list(self):
        self.assertEqual(self.cbqs[0]['path'], self.sample_list_data['items'][0]['path'])

    def test_data_is_fetched_from_cb_on_evaluate(self):
        # we're going with a lazy implementation - only when length or items are requested we're going to get stuff
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            # To avoid picklingerrors, we're going to mock the cache too
            with mock.patch('crunchbase.views.cache', cache=mock.Mock()) as c:
                c.get = mock.Mock(return_value=None)
                resp = mock.Mock()
                resp.json.return_value = self.sample_list_json
                req.get.return_value = resp
                qs = CrunchbaseQueryset(dataset_uri=self.dataset_uri)
                self.assertEqual(req.get.call_count, 0)
                len(qs)
                self.assertEqual(req.get.call_count, 1)
                item = qs[0]
                self.assertEqual(req.get.call_count, 1)

    def test_data_is_fetched_when_not_present_in_current_page(self):
        qs = CrunchbaseQueryset(dataset=self.sample_list_json, dataset_uri=self.dataset_uri)
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            with mock.patch('crunchbase.views.cache', cache=mock.Mock()) as c:
                c.get = mock.Mock(return_value=None)
                self.assertEqual(req.get.call_count, 0)
                len(qs)
                self.assertEqual(req.get.call_count, 0)  # The dataset is already present so no need to call
                item = qs[0]
                self.assertEqual(req.get.call_count, 0)  # As above
                # Now, we're going to try to fetch an item with an index greater than the available items, so
                item = qs[1001]
                req.get.assert_called_once_with(self.dataset_uri, params={'user_key': settings.CRUNCHBASE_USER_KEY,
                                                                          'page': 2})

    def test_items_from_following_pages_are_fetched_correctly(self):
        qs = CrunchbaseQueryset(dataset=self.sample_list_json, dataset_uri=self.dataset_uri)
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            resp = mock.Mock()
            resp.json.return_value = self.sample_list_json
            req.get.return_value = resp
            item = qs[0]
            # Now, we're going to try to fetch an item with an index greater than the available items, so
            new_page_json = self.sample_list_json.copy()
            new_page_json['data']['paging']['current_page'] = 2
            resp.json.return_value = new_page_json
            item = qs[1001]

    def test_dataset_is_cached(self):
        qs = CrunchbaseQueryset(dataset_uri=self.dataset_uri)
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            with mock.patch('crunchbase.views.cache', cache=mock.Mock()) as c:
                c.get = mock.Mock(return_value=None)
                c.set = mock.Mock(side_effect=lambda *args, **kwargs: cache.set(*args, **kwargs))
                req.get.return_value = self.page1
                item = qs[0]
                self.assertEqual(req.get.call_count, 1)
                # When retrieving from the second page, we have to make another GET
                req.get.return_value = self.page2
                item = qs[1002]
                self.assertEqual(req.get.call_count, 2)

            # Now, if we go back to page 1, we should not have to request again - it should be cached (we didn't mock set())
            req.get.return_value = self.page1  # This should not be called anyway
            item = qs[1]
            self.assertEqual(req.get.call_count, 2)
            # Going back to page 2...
            item = qs[1005]
            self.assertEqual(req.get.call_count, 2)

    def test_dataset_contains_paging_and_metadata_as_properties(self):
        qs = CrunchbaseQueryset(dataset_uri=self.dataset_uri)
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            with mock.patch('crunchbase.views.cache', cache=mock.Mock()) as c:
                c.get = mock.Mock(return_value=None)
                c.set = mock.Mock(side_effect=lambda *args, **kwargs: cache.set(*args, **kwargs))
                req.get.return_value = self.page1
                self.assertEqual(req.get.call_count, 0)
                self.assertDictEqual(qs.paging, self.page1.json()['data']['paging'])
                self.assertEqual(req.get.call_count, 1)
                self.assertDictEqual(qs.metadata, self.page1.json()['metadata'])
                self.assertEqual(req.get.call_count, 1)  # We really expect the cache to work here

    def test_dataset_can_be_sliced(self):
        def pick_page(*args, **kwargs):
            if 'page' in kwargs:
                if kwargs['page'] == 2:
                    return self.page2
                return requests.get(self.dataset_uri, params={'user_key': settings.CRUNCHBASE_USER_KEY, 'page': kwargs['page']})
            return self.page1
        qs = CrunchbaseQueryset(dataset_uri=self.dataset_uri)
        with mock.patch('crunchbase.views.requests', autospec=True) as req:
            req.get = mock.Mock(side_effect=pick_page)
            self.assertEqual(len(qs[:50]), 50)
            self.assertEqual(len(qs[100:200]), 100)
            self.assertEqual(len(qs[1050:1100]), 50)  # second page
            # I have decided that slicing across pages should not be permitted - I think I have a working solution but
            # the test output doesn't smell good to me, so I'll just go with an exception instead
            self.assertRaises(IndexError, lambda: len(qs[:2500]))

    def test_dataset_can_be_searched(self):
        qs = CrunchbaseQueryset(dataset_uri=self.dataset_uri)
        # We're gonna try to search the first item, and we expect to get a list with that item
        item = self.sample_list_data['items'][0]
        results = qs.search(item['name'])
        self.assertGreaterEqual(len(results), 1)
        self.assertIn(item['name'], [x['name'] for x in results])

    def test_dataset_items_search_detail_for_extra_information(self):
        qs = CrunchbaseQueryset(dataset_uri=self.dataset_uri)
        item = qs[0]
        self.assertTrue(item['properties__short_description'])
        # We're gonna start by matching exactly the requirements we used for the original list() implementation
        detail = CrunchbaseEndpoint(CrunchbaseQuery.ENDPOINTS['companies']).detail(item['path'])
        self.assertEqual(detail['data']['properties']['short_description'], item['properties__short_description'])
