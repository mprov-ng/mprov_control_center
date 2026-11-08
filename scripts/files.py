""" Which images a managed file reaches, and telling the admin they need a
rebuild to pick a change up (#519).  Like a change to scripts or Ansible, a
file change doesn't start builds by itself. """
from django.contrib import messages
from django.db.models import Q
from django.urls import reverse
from django.utils.html import format_html


def images_using(files):
    """ The system images that get any of these files: attached to the image,
    one of its system groups, or its OS distro. """
    from systems.models import SystemImage
    return SystemImage.objects.filter(
        Q(files__in=files) | Q(systemgroups__files__in=files) | Q(osdistro__files__in=files)
    ).distinct().order_by("name")


def images_of(layer):
    """ The system images built from this distro, group or image. """
    from systems.models import SystemImage
    name = layer._meta.model_name
    if name == "systemimage":
        return SystemImage.objects.filter(pk=layer.pk)
    if name == "systemgroup":
        return SystemImage.objects.filter(systemgroups=layer).order_by("name")
    return SystemImage.objects.filter(osdistro=layer).order_by("name")


def tell_rebuild(modeladmin, request, images, what):
    """ "N images use <what> and need a rebuild to pick it up: …" """
    images = list(images)
    if not images:
        return
    names = ", ".join(i.name for i in images[:10]) + (" …" if len(images) > 10 else "")
    one = len(images) == 1
    count = f"{len(images)} image" + ("" if one else "s")
    link = reverse("admin:systems_systemimage_changelist")
    modeladmin.message_user(request, format_html(
        "{} {} {} and {} a rebuild to pick the change up: {}. Rebuild {} from <a href=\"{}\">System Images</a>.",
        count, "uses" if one else "use", what, "needs" if one else "need", names, "it" if one else "them", link),
        messages.WARNING)


class FilesRebuildNoticeMixin:
    """ For the OS distro, system group and system image admins: after their
    managed files change, say which images need a rebuild. """

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if change and "files" in form.changed_data:
            tell_rebuild(self, request, images_of(form.instance), "changed managed files")
