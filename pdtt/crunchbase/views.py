from django.conf import settings
from django.core.cache import cache
from django.views.generic import ListView
import requests


class CrunchbaseSearchView(ListView):
    template_name = 'crunchbase/search_results.html'

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        data = super(CrunchbaseSearchView, self).get_context_data(**kwargs)
        companies = CrunchbaseQuery().companies.list(fetch_values=('properties__short_description',))['items']
        data['companies_search_results'] = companies
        return data


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


class CrunchbaseEndpoint(object):
    BASE_URI = 'http://api.crunchbase.com/v/2/'  # trailing slash, because the paths in the response data are like that
    uri = ''
    per_page = 10

    def __init__(self, uri):
        super(CrunchbaseEndpoint, self).__init__()
        self.uri = self.BASE_URI + uri

    def fetch_item_values(self, path, fetch_values):
        """

        :param path: item path as exposed in CrunchbaseEndpoint.list result
        :param fetch_values: iterable
        :return: :rtype: dict
        """
        # The actual method should include ways to parse the keys of the values to be fetched, but we can work with a
        # a map here
        values_map = {
            'properties__short_description': lambda detail: ('properties__short_description',
                                                             detail['properties']['short_description']),
        }
        item_details = self.detail(path)
        # The default behaviour could change to simply return the key that was passed as fetch_value, rather than raising an
        # exception, but that would make it harder to test
        item_values = [values_map.get(v)(item_details) for v in fetch_values]
        return dict(item_values)

    def list(self, per_page=None, raw=False, fetch_values=None):
        """


        :param fetch_values: Iterable with the names of the detail values to be fetched here
        :param per_page: Number of items to return per page (defaults to CrunchbaseEndpoint.per_page)
        :param raw: Boolean to indicate if the result should be the actual response or the processed list

        The output JSON of a Crunchbase list verb has a {metadata: {}, data: {items: [], paging: {}} structure;
        at the moment we don't care about anything else than the actual items

        """
        cache_key = self.uri  # TODO: This will need to take the page into consideration
        response = cache.get(cache_key)
        if response is None:
            response = requests.get(self.uri, params={'user_key': settings.CRUNCHBASE_USER_KEY})
            # TODO: I suspect that setting the whole response in cache might cause problems with the cache value size
            # since the actual response is roughly 200k in size. Still, apparently, in normal use everything gets properly
            # cached, so...
            cache.set(cache_key, response)

        if raw:  # In this case, we will return the actual output of the GET request, without any processing
            return response

        data = response.json()['data']
        per_page = self.per_page if per_page is None else per_page
        if per_page:
            data['items'] = data['items'][:per_page]
        if fetch_values is not None:
            for item in data['items']:
                item.update(self.fetch_item_values(item['path'], fetch_values))
        return data

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
        return response.json()['data']