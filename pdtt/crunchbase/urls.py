from django.conf.urls import patterns, include, url
from crunchbase.views import CrunchbaseSearchView


urlpatterns = patterns(
    '',
    url(r'^search/$', CrunchbaseSearchView.as_view(), name='search'),
)
