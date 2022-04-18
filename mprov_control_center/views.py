from common.views import MProvView

# Default view for the index.
class IndexAPIView(MProvView):
    template = 'docs.html'