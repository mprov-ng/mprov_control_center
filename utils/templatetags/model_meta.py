from django import template
register = template.Library()

@register.simple_tag
def get_docstring(cl):
  """
  Returns the docstring for the instance.
  """
  return cl.model.__doc__