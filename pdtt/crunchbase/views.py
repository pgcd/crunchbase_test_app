from django.views.generic import ListView


class CrunchbaseSearchView(ListView):
    template_name = 'crunchbase/search_results.html'
    
    def get_queryset(self):
        return []