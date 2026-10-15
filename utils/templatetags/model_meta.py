from django import template
register = template.Library()

@register.simple_tag
def get_docstring(cl):
  """
  Returns the docstring of the changelist's model (cl.model), or None if it is
  only Django's auto-generated "ClassName(fields...)" docstring.
  """
  docString = cl.model.__doc__
  if docString.startswith("\n"):
    docString = docString[1:]

  # remove docstrings that contain only the class definition.
  testString = str(cl.model.__name__) + "("
  
  if docString.startswith(testString):
    docString=None
  
  return docString