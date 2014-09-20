from django.conf.urls import patterns, include, url


urlpatterns = patterns(
    '',
    (r'', include('crunchbase.urls', namespace='crunchbase'))
)
