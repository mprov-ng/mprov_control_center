""" Rendering a managed file that's a Jinja template, for one image (#519).

The context is the image's merged Configuration Parameters as `params`, the
image as `image` ({name, slug}) and its distro as `distro` ({name,
version}).  Rendering is sandboxed, and an undefined variable is an error,
not an empty string, so a typo fails the build instead of shipping a
half-filled file. """
from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

ENVIRONMENT = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)


def context_for(image):
    from common import flat_config, render_config
    config = flat_config(render_config(image))
    distro = image.osdistro
    return {
        "params": config.get("config_params", {}),
        "image": {"name": image.name, "slug": image.slug},
        "distro": {"name": distro.name, "version": distro.version} if distro is not None else {},
    }


def content(item):
    """ The uploaded file's bytes. """
    item.filename.open("rb")
    try:
        return item.filename.read()
    finally:
        item.filename.close()


def render(item, image):
    """ (bytes, None) for this file as placed into this image, or (None, error).
    A file that isn't a template is returned as it is. """
    try:
        data = content(item)
    except OSError as e:
        return None, f"{item.slug}: the uploaded file can't be read ({e.__class__.__name__})."
    if not item.template:
        return data, None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"{item.slug}: a template must be UTF-8 text."
    try:
        return ENVIRONMENT.from_string(text).render(**context_for(image)).encode("utf-8"), None
    except TemplateError as e:
        line = f" (line {e.lineno})" if getattr(e, "lineno", None) else ""
        return None, f"{item.slug}: {e.__class__.__name__}{line}: {e.message if hasattr(e, 'message') else e}"
