import collections
from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.http import Http404
from django.views.generic import ListView
from math import ceil
import requests


class CrunchbasePaginator(Paginator):
    def __init__(self, object_list, per_page, orphans=0, allow_empty_first_page=True, **kwargs):
        # We need to override this to set the correct number of 1000-items pages
        super(CrunchbasePaginator, self).__init__(object_list, per_page, orphans, allow_empty_first_page)
        self._count = kwargs.pop('actual_objects_count')
        self._num_pages = int(ceil(self._count / per_page))


class CrunchbaseSearchView(ListView):
    template_name = 'crunchbase/search_results.html'
    context_object_name = 'search_results'
    subset = None
    paginate_by = 10

    def get_paginator(self, queryset, per_page, orphans=0, allow_empty_first_page=True, **kwargs):
        kwargs['actual_objects_count'] = self.cb_page_data.get('items_per_page', 0) * self.cb_page_data.get('number_of_pages', 0)
        return CrunchbasePaginator(queryset, per_page, orphans, allow_empty_first_page, **kwargs)

    def __init__(self, **kwargs):
        super(CrunchbaseSearchView, self).__init__(**kwargs)
        self.crunchbase = CrunchbaseQuery()
        self.cb_page_data = {}  # CrunchBase original pagination data

    def dispatch(self, request, *args, **kwargs):
        if kwargs.get('subset'):
            self.subset = getattr(self.crunchbase, kwargs['subset'])
        return super(CrunchbaseSearchView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        subset_list = self.subset.datastore
        self.cb_page_data = subset_list.paging
        return subset_list

        # def paginate_queryset(self, queryset, page_size):
        # paginator, page, page.object_list, is_paginated = super(CrunchbaseSearchView, self).paginate_queryset(queryset,
        # page_size)
        # # Since subset.list() returns a page-sized object, Django wouldn't activate the pagination (because the list is
        # the same
        # # size as the page). To force it to consider it paginable, we must return True as is_paginated.
        #     return paginator, page, page.object_list, True


class CrunchbaseHomeSearchView(CrunchbaseSearchView):
    def get_context_data(self, **kwargs):
        data = super(CrunchbaseSearchView, self).get_context_data(**kwargs)
        companies = self.crunchbase.companies.list(fetch_values=('properties__short_description', 'primary_image'))
        data['companies_search_results'] = companies['data']['items']
        products = self.crunchbase.products.list(fetch_values=('properties__short_description', 'primary_image'))
        data['products_search_results'] = products['data']['items']
        return data

    def get_queryset(self):
        return []


class CrunchbaseQuery(object):
    ENDPOINTS = {'companies': 'organizations', 'products': 'products'}

    def list_endpoint_uris(self):
        """
        This method returns a list of the "exported" endpoints' URIs

        :return: :rtype: dict
        """
        return self.ENDPOINTS

    def __getattr__(self, item):
        if item in self.ENDPOINTS:
            return CrunchbaseEndpoint(self.ENDPOINTS[item])
        raise AttributeError


class CrunchbaseQueryset(collections.Sequence):
    total_items = None

    def __init__(self, dataset=None, dataset_uri=None):
        assert dataset or dataset_uri, "Either dataset_uri or dataset must be defined"  # dataset should only be used for testing
        self._dataset = dataset
        self._dataset_uri = dataset_uri

    def get_dataset(self, **kwargs):
        kwargs.update({'user_key': settings.CRUNCHBASE_USER_KEY})
        cache_key = "%s-%s" % (kwargs.get('page', 1), self._dataset_uri)
        response = cache.get(cache_key)
        if response is None:
            response = requests.get(self._dataset_uri, params=kwargs)
            # TODO: I suspect that setting the whole response in cache might cause problems with the cache value size
            # since the actual response is roughly 200k in size. Still, apparently, in normal use everything gets properly
            # cached, so...
            cache.set(cache_key, response)
        return response.json()

    @property
    def dataset(self):
        if not self._dataset:  # We initialize the dataset with the first page
            self._dataset = self.get_dataset()
        return self._dataset

    @property
    def paging(self):
        return self.dataset['data']['paging']

    @property
    def metadata(self):
        return self.dataset['metadata']

    def __getitem__(self, index):
        per_page = self.paging['items_per_page']
        if isinstance(index, slice):
            # TODO: Consider the multiple page scenario (eg. [500:1500]
            start, stop, step = index.indices(self.paging['total_items'])
            expected_start_page = int(ceil(start / per_page)) + 1
            expected_end_page = int(ceil(stop / per_page)) + 1
            if expected_start_page != self.paging['current_page']:
                self._dataset = self.get_dataset(page=expected_start_page)
            if expected_end_page > expected_start_page:
                raise IndexError("Slicing across pages is not allowed")
                # self.extend_dataset(expected_start_page, expected_end_page)
            adjustment = (expected_start_page - 1) * per_page
            adjusted_index = slice(start - adjustment, stop - adjustment, None)
        else:
            expected_start_page = int(ceil(index / per_page)) + 1
            if expected_start_page != self.paging['current_page']:
                self.get_dataset(page=expected_start_page)
            adjusted_index = index - (expected_start_page - 1) * per_page
        return self.dataset['data']['items'][adjusted_index]

    def __len__(self):
        return self.paging['total_items']

    def extend_dataset(self, start_page, end_page):
        # This seems to work but I just can't bring myself to actually trust it, so I guess I'm gonna raise an exception instead
        fetched_pages = int(len(self.dataset['data']['items']) / self.paging['items_per_page'])
        for i in range(start_page + fetched_pages, end_page + 1):  # end_page is inclusive
            ds = self.get_dataset(page=i)
            self._dataset['data']['items'].extend(ds['data']['items'])


class CrunchbaseEndpoint(object):
    BASE_URI = 'http://api.crunchbase.com/v/2/'  # trailing slash, because the paths in the response data are like that
    uri = ''
    per_page = 10

    def __init__(self, uri):
        super(CrunchbaseEndpoint, self).__init__()
        self.uri = self.BASE_URI + uri
        self.datastore = CrunchbaseQueryset(dataset_uri=self.uri)

    def fetch_item_values(self, path, fetch_values):
        """

        :param path: item path as exposed in CrunchbaseEndpoint.list result
        :param fetch_values: iterable
        :return: :rtype: dict
        """

        def get_primary_image(detail):
            # Helper to deal with missing images and image base url
            try:
                image_path = detail['data']['relationships']['primary_image']['items'][0]['path']
            except KeyError:
                image_path = None
            else:
                image_path = detail['metadata']['image_path_prefix'] + image_path
            return 'primary_image', image_path

        # The actual method should include ways to parse the keys of the values to be fetched, but we can work with a
        # a map here
        values_map = {
            'properties__short_description': lambda detail: ('properties__short_description',
                                                             detail['data']['properties']['short_description']),
            # In this case, I'm gonna use a shorthand, since the actual key would be unwieldy
            'primary_image': get_primary_image
        }
        item_details = self.detail(path)
        # The default behaviour could change to simply return the key that was passed as fetch_value, rather than raising an
        # exception, but that would make it harder to test
        item_values = [values_map.get(v)(item_details) for v in fetch_values]
        return dict(item_values)

    def list(self, per_page=None, page=0, raw=False, fetch_values=None):
        """

        :param page: 0-based index of the page
        :param fetch_values: Iterable with the names of the detail values to be fetched here
        :param per_page: Number of items to return per page (defaults to CrunchbaseEndpoint.per_page)
        :param raw: Boolean to indicate if the result should be the actual response or the processed list

        The output JSON of a Crunchbase list verb has a {metadata: {}, data: {items: [], paging: {}} structure;
        at the moment we don't care about anything else than the actual items

        """
        per_page = per_page or self.per_page  # Allowing to use CBs page size default doesn't really make sense.
        crunchbase_page = int((page * per_page) / 1000)  # TODO: Refactor this so that it's not hardcoded
        # We're gonna work on the crunchbase page, so our index needs to be adjusted
        page_index = (page * per_page) - (1000 * crunchbase_page)

        cache_key = "%s-%s" % (crunchbase_page, self.uri)
        response = cache.get(cache_key)
        if response is None:
            response = requests.get(self.uri, params={'user_key': settings.CRUNCHBASE_USER_KEY, 'page': crunchbase_page + 1})
            # TODO: I suspect that setting the whole response in cache might cause problems with the cache value size
            # since the actual response is roughly 200k in size. Still, apparently, in normal use everything gets properly
            # cached, so...
            cache.set(cache_key, response)

        if raw:  # In this case, we will return the actual output of the GET request, without any processing
            return response

        response_json = response.json()
        # Annoyingly, CB API returns a 200 Ok status even for errors, so we have to dig into the result set and raise accordingly
        self.handle_errors(response_json)
        response_json['data']['items'] = response_json['data']['items'][page_index:page_index + per_page]
        # Instead of updating the original current_page value, we're adding a new one to allow further processing
        response_json['data']['paging'].update({'per_page': per_page, 'page': page})
        if fetch_values is not None:
            for item in response_json['data']['items']:
                item.update(self.fetch_item_values(item['path'], fetch_values))
        return response_json

    def detail(self, path, raw=False):
        # This method should probably belong to a different class, or the class should be renamed; still, it's handy to keep it
        # here for the moment
        """

        :param path: "Permalink" for the required resource in the form /resource/identifier (eg. /companies/virgil-security)
        """
        response = cache.get(path)
        if response is None:
            response = requests.get(self.BASE_URI + path, params={'user_key': settings.CRUNCHBASE_USER_KEY})
            cache.set(path, response)

        if raw:
            return response
        return response.json()

    def handle_errors(self, response_json):
        """
        :param response_json:
        :raise Http404:
        """
        # We could check here for different types of errors and deal with them differently
        response_error = response_json['data'].get('error')
        if response_error:
            raise Http404