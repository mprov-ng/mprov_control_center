
from .views import *
import yaml


def parse_config_params(params_obj):
  tmpYamlDict = {}
  yaml_merged = {}
  if hasattr(params_obj, 'osdistro'):
    tmpYamlDict = yaml.safe_load(params_obj.osdistro.config_params)
    if tmpYamlDict is not None:
      try:
        if type(tmpYamlDict) is list:
          for dict_entry in tmpYamlDict:
            yaml_merged.update(dict_entry)
        else: 
            yaml_merged.update(tmpYamlDict)
      except:
        pass
    
  if hasattr(params_obj, 'systemgroups'):
    for group in params_obj.systemgroups:
      tmpYamlDict = yaml.safe_load(group.config_params)
      if tmpYamlDict is not None:
        try:
          if type(tmpYamlDict) is list:
            for dict_entry in tmpYamlDict:
              yaml_merged.update(dict_entry)
          else: 
              yaml_merged.update(tmpYamlDict)
        except:
          pass

  if hasattr(params_obj, 'config_params'):
    if type(params_obj.config_params) is dict:
      tmpYamlDict = params_obj.config_params
    else:
      tmpYamlDict = yaml.safe_load(params_obj.config_params)
    # print(tmpYamlDict)
    if tmpYamlDict is not None:
      try:
        if type(tmpYamlDict) is list:
          for dict_entry in tmpYamlDict:
            yaml_merged.update(dict_entry)
        else: 
          yaml_merged.update(tmpYamlDict)
      except:
        pass
      
  return yaml_merged