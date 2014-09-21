from django.conf import settings
from django.views.generic import ListView
import requests


class CrunchbaseSearchView(ListView):
    template_name = 'crunchbase/search_results.html'

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        data = super(CrunchbaseSearchView, self).get_context_data(**kwargs)
        data['companies_search_results'] = CrunchbaseQuery().companies.list().json()['data']['items']
        return data


class CrunchbaseQuery(object):
    ENDPOINTS = {'companies': '/v/2/organizations', 'products': '/v/2/products'}
    BASE_URI = 'http://api.crunchbase.com'

    def list_endpoint_uris(self):
        """
        This method returns a list of the "exported" endpoints' URIs

        :return: :rtype: dict
        """
        return self.ENDPOINTS

    def __getattr__(self, item):
        if item in self.ENDPOINTS:
            return CrunchbaseEndpoint(self.BASE_URI+self.ENDPOINTS[item])
        raise AttributeError


class CrunchbaseEndpoint(object):
    uri = ''

    def __init__(self, uri):
        super(CrunchbaseEndpoint, self).__init__()
        self.uri = uri

    def list(self):
        """
        The output JSON of a Crunchbase list verb has a {metadata: {}, data: {items: [], paging: {}} structure;
        at the moment we don't care about anything else than the actual items
        This method returns the actual items returned by a GET on this endpoint.

        """
        return requests.get(self.uri, params={'user_key': settings.CRUNCHBASE_USER_KEY})