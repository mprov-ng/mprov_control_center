
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

def render_config(obj):
  configDict = {}
  tmpDict = {}

  print(type(obj).__name__)
  if type(obj).__name__ == 'System':
    if obj.systemimage is not None:
      setattr(obj, 'osdistro', obj.systemimage.osdistro)


  # collect distro config
  if hasattr(obj, "osdistro"):
    configDict['osdistro']=dict()
    configDict['osdistro']['params'] = yaml.safe_load(obj.osdistro.config_params)
    configDict['osdistro']['ansibleplaybooks'] = obj.osdistro.ansibleplaybooks
    configDict['osdistro']['ansibleroles'] = obj.osdistro.ansibleroles
    configDict['osdistro']['ansiblecollections'] = obj.osdistro.ansiblecollections
    configDict['osdistro']['install_kernel_cmdline'] = obj.osdistro.install_kernel_cmdline
    configDict['osdistro']['tmpfs_root_size'] = obj.osdistro.tmpfs_root_size
    configDict['osdistro']['initial_mods'] = obj.osdistro.initial_mods
    configDict['osdistro']['prov_interface'] = obj.osdistro.prov_interface
  
  # collect all system group configs
  if hasattr(obj, 'systemgroups'):
    for group in obj.systemgroups.all():
      configDict[group.name]=dict()
      configDict[group.name]['params'] = yaml.safe_load(group.config_params)
      configDict[group.name]['ansibleplaybooks'] = group.ansibleplaybooks
      configDict[group.name]['ansibleroles'] = group.ansibleroles
      configDict[group.name]['ansiblecollections'] = group.ansiblecollections
      configDict[group.name]['install_kernel_cmdline'] = group.install_kernel_cmdline
      configDict[group.name]['tmpfs_root_size'] = group.tmpfs_root_size
      configDict[group.name]['initial_mods'] = group.initial_mods
      configDict[group.name]['prov_interface'] = group.prov_interface

  # finally, collect node configs.
  configDict['object'] = dict()
  configDict['object']['params'] = yaml.safe_load(obj.config_params)
  configDict['object']['ansibleplaybooks'] = obj.ansibleplaybooks
  configDict['object']['ansibleroles'] = obj.ansibleroles
  configDict['object']['ansiblecollections'] = obj.ansiblecollections
  configDict['object']['install_kernel_cmdline'] = obj.install_kernel_cmdline
  configDict['object']['tmpfs_root_size'] = obj.tmpfs_root_size
  configDict['object']['initial_mods'] = obj.initial_mods
  configDict['object']['prov_interface'] = obj.prov_interface
  

  # now let's do the merge.
  tmpDict['params'] = dict()
  tmpDict['ansibleplaybooks'] = dict()
  tmpDict['ansibleroles'] = dict()
  tmpDict['ansiblecollections'] = dict()
  tmpDict['install_kernel_cmdline'] = dict()
  tmpDict['install_kernel_cmdline'] = dict()
  tmpDict['tmpfs_root_size'] = dict()
  tmpDict['initial_mods'] = dict()
  tmpDict['prov_interface'] = dict()

  # first, merge distro
  if 'osdistro' in configDict.keys():
    tmpDict['params']['source'] = 'osdistro'
    tmpDict['params']['value'] = configDict['osdistro']['params']
    
    
    tmpDict['ansibleplaybooks']['source'] = 'osdistro'
    tmpDict['ansibleplaybooks']['value'] = configDict['osdistro']['ansibleplaybooks']

    
    tmpDict['ansibleroles']['source'] = 'osdistro'
    tmpDict['ansibleroles']['value'] = configDict['osdistro']['ansibleroles']

    
    tmpDict['ansiblecollections']['source'] = 'osdistro'
    tmpDict['ansiblecollections']['value'] = configDict['osdistro']['ansiblecollections']

    
    tmpDict['install_kernel_cmdline']['source'] = 'osdistro'
    tmpDict['install_kernel_cmdline']['value'] = configDict['osdistro']['install_kernel_cmdline']

    
    tmpDict['tmpfs_root_size']['source'] = 'osdistro'
    tmpDict['tmpfs_root_size']['value'] = configDict['osdistro']['tmpfs_root_size']

    
    tmpDict['initial_mods']['source'] = 'osdistro'
    tmpDict['initial_mods']['value'] = configDict['osdistro']['initial_mods']

    
    tmpDict['prov_interface']['source'] = 'osdistro'
    tmpDict['prov_interface']['value'] = configDict['osdistro']['prov_interface']

  # now let's merge the systemgroups
  for group in obj.systemgroups.all():
    if configDict[group.name]['params'] != "" and configDict[group.name]['params'] is not None:
      tmpDict['params']['source'] = group.name
      tmpDict['params']['value'] = configDict[group.name]['params']

    if configDict[group.name]['ansibleplaybooks'] != "" and configDict[group.name]['ansibleplaybooks'] is not None:
      tmpDict['ansibleplaybooks']['source'] = group.name
      tmpDict['ansibleplaybooks']['value'] = configDict[group.name]['ansibleplaybooks']

    if configDict[group.name]['ansibleroles'] != "" and configDict[group.name]['ansibleroles'] is not None:
      tmpDict['ansibleroles']['source'] = group.name
      tmpDict['ansibleroles']['value'] = configDict[group.name]['ansibleroles']

    if configDict[group.name]['ansiblecollections'] != "" and configDict[group.name]['ansiblecollections'] is not None:
      tmpDict['ansiblecollections']['source'] = group.name
      tmpDict['ansiblecollections']['value'] = configDict[group.name]['ansiblecollections']

    if configDict[group.name]['install_kernel_cmdline'] != "" and configDict[group.name]['install_kernel_cmdline'] is not None:
      tmpDict['install_kernel_cmdline']['source'] = group.name
      tmpDict['install_kernel_cmdline']['value'] = configDict[group.name]['install_kernel_cmdline']

    if configDict[group.name]['tmpfs_root_size'] != "" and configDict[group.name]['tmpfs_root_size'] is not None:
      tmpDict['tmpfs_root_size']['source'] = group.name
      tmpDict['tmpfs_root_size']['value'] = configDict[group.name]['tmpfs_root_size']

    if configDict[group.name]['initial_mods'] != "" and configDict[group.name]['initial_mods'] is not None:
      tmpDict['initial_mods']['source'] = group.name
      tmpDict['initial_mods']['value'] = configDict[group.name]['initial_mods']

    if configDict[group.name]['prov_interface'] != "" and configDict[group.name]['prov_interface'] is not None:
      tmpDict['prov_interface']['source'] = group.name
      tmpDict['prov_interface']['value'] = configDict[group.name]['prov_interface']


  # finally merge the stuff on the node.
  if configDict['object']['params'] != "" and configDict['object']['params'] is not None:
    tmpDict['params']['source'] = 'self'
    tmpDict['params']['value'] = configDict['object']['params']

  if configDict['object']['ansibleplaybooks'] != "" and configDict['object']['ansibleplaybooks'] is not None:
    tmpDict['ansibleplaybooks']['source'] = 'self'
    tmpDict['ansibleplaybooks']['value'] = configDict['object']['ansibleplaybooks']

  if configDict['object']['ansibleroles'] != "" and configDict['object']['ansibleroles'] is not None:
    tmpDict['ansibleroles']['source'] = 'self'
    tmpDict['ansibleroles']['value'] = configDict['object']['ansibleroles']

  if configDict['object']['ansiblecollections'] != "" and configDict['object']['ansiblecollections'] is not None:
    tmpDict['ansiblecollections']['source'] = 'self'
    tmpDict['ansiblecollections']['value'] = configDict['object']['ansiblecollections']

  if configDict['object']['install_kernel_cmdline'] != "" and configDict['object']['install_kernel_cmdline'] is not None:
    tmpDict['install_kernel_cmdline']['source'] = 'self'
    tmpDict['install_kernel_cmdline']['value'] = configDict['object']['install_kernel_cmdline']

  if configDict['object']['tmpfs_root_size'] != 0 and configDict['object']['tmpfs_root_size'] is not None:
    tmpDict['tmpfs_root_size']['source'] = 'self'
    tmpDict['tmpfs_root_size']['value'] = configDict['object']['tmpfs_root_size']

  if configDict['object']['initial_mods'] != "" and configDict['object']['initial_mods'] is not None:
    tmpDict['initial_mods']['source'] = 'self'
    tmpDict['initial_mods']['value'] = configDict['object']['initial_mods']

  if configDict['object']['prov_interface'] != "" and configDict['object']['prov_interface'] is not None:
    tmpDict['prov_interface']['source'] = 'self'
    tmpDict['prov_interface']['value'] = configDict['object']['prov_interface']
 
  return tmpDict

