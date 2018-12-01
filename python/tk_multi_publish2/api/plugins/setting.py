# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import collections
import copy

import sgtk
from sgtk.platform import create_setting

logger = sgtk.platform.get_logger(__name__)

def get_setting_for_context(setting_key, context=None, plugin_schema={}):
    """
    """
    # the current bundle (the publisher instance)
    app = sgtk.platform.current_bundle()

    # Set the context if not specified
    context = context or app.context

    logger.debug("Finding plugin setting '%s' for context: %s" % (setting_key, context))

    # find the matching raw app settings for this context
    context_settings = sgtk.platform.engine.find_app_settings(
        app.engine.name,
        app.name,
        app.sgtk,
        context,
        app.engine.instance_name
    )

    # No settings found, raise an error
    if not context_settings:
        raise TankError("Cannot find settings for %s for context %s" % (app.name, context))

    if len(context_settings) > 1:
        # There's more than one instance of the app for the engine instance, so we'll
        # need to deterministically pick one. We'll pick the one with the same
        # application instance name as the current app instance.
        for settings in context_settings:
            if settings.get("app_instance") == app.instance_name:
                app_settings = settings
                break
    else:
        app_settings = context_settings[0]

    if not app_settings:
        raise TankError(
            "Search for %s settings for context %s yielded too "
            "many results (%s), none named '%s'" % (app.name, context,
            ", ".join([s.get("app_instance") for s in context_settings]),
            app.instance_name)
        )

    new_env = app_settings["env_instance"]
    new_eng = app_settings["engine_instance"]
    new_app = app_settings["app_instance"]
    new_settings = app_settings["settings"]
    new_descriptor = new_env.get_app_descriptor(new_eng, new_app)

    # Inject the plugin's schema for proper settings resolution
    schema = copy.deepcopy(new_descriptor.configuration_schema)
    dict_merge(schema, plugin_schema)

    # Create a new app instance for the new context
    app_obj = sgtk.platform.application.get_application(
            app.engine,
            new_descriptor.get_path(),
            new_descriptor,
            new_settings,
            new_app,
            new_env,
            context)

    setting_value = new_settings.get(setting_key)
    setting_schema = schema.get(setting_key)

    return create_setting(setting_key, setting_value, setting_schema, app_obj)

# At present, there is no way to override the configuration_schema on a
# descriptor object, hence we cannot use the app object's settings dict
# since it will lack our injected plugin schema data. The workaround is
# to create a new Setting object, which is less efficient.
#    # Return the context-specific app instance's setting value
#    return app_obj.settings.get(setting_key)

def dict_merge(dct, merge_dct):
    """ Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
    updating only top-level keys, dict_merge recurses down into dicts nested
    to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
    ``dct``.
    :param dct: dict onto which the merge is executed
    :param merge_dct: dct merged into dct
    :return: None
    """
    for k, v in merge_dct.iteritems():
        if (k in dct and isinstance(dct[k], dict)
                and isinstance(merge_dct[k], collections.Mapping)):
            dict_merge(dct[k], merge_dct[k])
        else:
            dct[k] = merge_dct[k]
