from django.conf import settings
from django.core.cache import cache
from django.http import Http404
from django.views.generic import ListView
import requests


class CrunchbaseSearchView(ListView):
    template_name = 'crunchbase/search_results.html'
    context_object_name = 'search_results'
    subset = None

    def __init__(self, **kwargs):
        super(CrunchbaseSearchView, self).__init__(**kwargs)
        self.crunchbase = CrunchbaseQuery()

    def dispatch(self, request, *args, **kwargs):
        self.subset = kwargs.get('subset')
        return super(CrunchbaseSearchView, self).dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return getattr(self.crunchbase, self.subset).list()['data']['items']


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