from django.conf import settings
from django.views.generic import ListView
import requests


class CrunchbaseSearchView(ListView):
    template_name = 'crunchbase/search_results.html'

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        data = super(CrunchbaseSearchView, self).get_context_data(**kwargs)
        data['companies_search_results'] = CrunchbaseQuery().companies.list()['items']
        return data


class CrunchbaseQuery(object):
    ENDPOINTS = {'companies': '/v/2/organizations', 'products': '/v/2/products'}

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
    BASE_URI = 'http://api.crunchbase.com'
    uri = ''
    per_page = 10

    def __init__(self, uri):
        super(CrunchbaseEndpoint, self).__init__()
        self.uri = self.BASE_URI+uri

    def list(self, per_page=None, raw=False):
        """

        :param per_page: Number of items to return per page (defaults to CrunchBase's own default)
        :param raw: Boolean to indicate if the result should be the actual response or the processed list

        The output JSON of a Crunchbase list verb has a {metadata: {}, data: {items: [], paging: {}} structure;
        at the moment we don't care about anything else than the actual items

        """
        response = requests.get(self.uri, params={'user_key': settings.CRUNCHBASE_USER_KEY})
        if raw:  # In this case, we will return the actual output of the GET request, without any processing
            return response

        data = response.json()['data']
        per_page = self.per_page if per_page is None else per_page
        if per_page:
            data['items'] = data['items'][:per_page]
        return data