""" An image's copy of a managed file (#519).

GET /systemimages/<image>/files/<file>/ returns the file as it's placed into
that image: a template rendered with the image's merged Configuration
Parameters, anything else as uploaded.  422 with the Jinja error for a
template that doesn't render, 404 for a file the image doesn't get.

Job servers read it with their certificate while building the image; a
person needs view permission on files and system images, since a rendered
file holds Configuration Parameters values. """
from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from common import render_config
from common.permissions import MProvPermission
from systems.models import SystemImage


class SystemImageFileView(APIView):
    permission_classes = [MProvPermission]
    mprov_permissions = {"GET": ["scripts.view_file", "systems.view_systemimage"]}

    def get(self, request, pk, slug):
        from scripts.templating import render
        image = SystemImage.objects.filter(pk=pk).first()
        if image is None:
            return Response({"detail": "No such image."}, status=404)
        entry = next((e for e in render_config(image)['files'] if e['item'].slug == slug), None)
        if entry is None:
            return Response({"detail": f"{image.slug} doesn't get a file {slug!r}."}, status=404)
        data, error = render(entry['item'], image)
        if error:
            return Response({"detail": error}, status=422)
        response = HttpResponse(data, content_type="application/octet-stream")
        response["X-mProv-File-Version"] = str(entry['item'].version)
        return response
