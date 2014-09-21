from django.views.generic import ListView




class CrunchbaseSearchView(ListView):
    template_name = 'crunchbase/search_results.html'

    def get_queryset(self):
        return []

    def get_context_data(self, **kwargs):
        data = super(CrunchbaseSearchView, self).get_context_data(**kwargs)
        data['companies_search_results'] = None
        return data


class CrunchbaseQuery(object):
    ENDPOINTS = {'companies': '', 'products': ''}

    def list_endpoints(self):
        return self.ENDPOINTS

    def __getattr__(self, item):
        if item in self.ENDPOINTS:
            return self.ENDPOINTS[item]
        raise AttributeError