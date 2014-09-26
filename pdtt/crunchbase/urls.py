from django.conf.urls import patterns, include, url
from crunchbase.views import CrunchbaseSearchView, CrunchbaseHomeSearchView, CrunchbaseDetailView


urlpatterns = patterns(
    '',
    url(r'^search/$', CrunchbaseHomeSearchView.as_view(), name='search'),
    url(r'^search/(?P<subset>companies|products)/$', CrunchbaseSearchView.as_view(), name='search'),
    url(r'^detail/(?P<path>.+)/$', CrunchbaseDetailView.as_view(), name='detail'),
)
