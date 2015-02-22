#! /usr/bin/python

import json

configuration_filename = "/etc/muther.ini"

def write(updated_config):
    """ 
    Write the configuration.  
    Pass in the entire configuration to be saved.
    """
    global configuration_filename
    print "writing configuration_filename = " + configuration_filename

    original_config =  json.loads(open(configuration_filename, "r").read())
    config = dict(updated_config.items() + original_config.items())
    new_config_string = json.dumps(config, sort_keys=True, indent=4)
    open(configuration_filename , "w").write(new_config_string)

def read(field = None):
    """ 
    Read in the configuration.  
    Pass in the fieldname of interest, otherwise the entire configuarion will 
    be returned.
    """
    global configuration_filename
    print "reading configuration_filename = " + configuration_filename

    config = json.loads(open(configuration_filename, "r").read())
    if field == None:
        return config
    else:
        return config[field] if field in config else None

def use_file(filename):
    """ 
    Read in the configuration.  
    Pass in the fieldname of interest, otherwise the entire configuarion will 
    be returned.
    """
    global configuration_filename
    configuration_filename = filename
