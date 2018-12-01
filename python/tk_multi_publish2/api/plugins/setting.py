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
from ..data import PublishData

logger = sgtk.platform.get_logger(__name__)

def create_plugin_setting(name, value, schema):
    """
    """
    schema = schema or {}
    setting_type = schema.get("type")
    if setting_type == "list":
        return ListPluginSetting(name, value, schema)
    elif setting_type == "dict":
        return DictPluginSetting(name, value, schema)
    else:
        return PluginSetting(name, value, schema)

class PluginSetting(object):
    """
    This class provides an interface to settings defined for a given
    :ref:`publish-api-task`.
    """

    def __init__(self, name, value, schema):
        """
        This class derives from :ref:`publish-api-data`.  A few special keys
        are set by default and are accessible after initialization. Those keys
        are:

        * ``default_value``: The default value as configured for this setting.
        * ``description``: Any description provided for this setting in the config.
        * ``name``: The display name for this setting.
        * ``type``: The type for this setting (:py:attr:`bool`, :py:attr:`str`, etc).
        * ``value``: The current value of this setting.

        .. note:: There is typically no need to create instances of this class
            manually. Each :ref:`publish-api-task` will expose a dictionary of
            configured ``PluginSettings``.
        """

        self._name = name
        self._schema = schema or {}
        self._value = value
        self._type = self._schema.get("type")
        self._default_value = self._schema.get("default_value")
        self._description = self._schema.get("description")

        # Process the children
        self._process_children()

    def _process_children(self):
        """
        Process an update to this setting's value
        """
        pass

    def __repr__(self):
        return "<%s %s: %s>" % (self.__class__.__name__, self._name, self._value)

    def __str__(self):
        return str(self._value)

    def __eq__(self, other):
        if other is self:
            return True
        if other is None:
            return False
        if isinstance(other, PluginSetting):
            return self._value == other._value
        return self._value == other

    def __contains__(self, key):
        return key in self._value

    @property
    def name(self):
        """
        The setting name
        """
        return self._name

    @property
    def value(self):
        """
        The current value of the setting
        """
        return self._value

    @value.setter
    def value(self, value):
        """
        The the value of the PluginSetting
        """
        if value != self._value:
            # TODO: Validate the value first
            self._value = value
            self._process_children()

    @property
    def string_value(self):
        """
        The setting value, as a string
        """
        return str(self)

    @property
    def description(self):
        """
        The description of the setting
        """
        return self._description

    @property
    def default_value(self):
        """
        The default value of the setting.
        """
        return self._default_value

    @property
    def type(self):
        """
        The data type of the setting.
        """
        return self._type


class ListPluginSetting(PluginSetting, collections.Sequence):
    """
    """
    def __init__(self, name, value, schema):
        """
        """
        collections.Sequence.__init__(self)
        PluginSetting.__init__(self, name, value, schema)

    def _process_children(self):
        """
        Process an update to this setting's children
        """
        self._children = []
        value_schema = self._schema.get("values", {})
        for i, sub_value in enumerate(self._value):
            value_name = "%s[%s]" % (self._name, str(i))
            self._children.append(create_plugin_setting(value_name, sub_value, value_schema))

    def __getitem__(self, key):
        return self._children[key]

    def __len__(self):
        return len(self._children)


class DictPluginSetting(PluginSetting, collections.Mapping):
    """
    """
    def __init__(self, name, value, schema):
        """
        """
        collections.Mapping.__init__(self)
        PluginSetting.__init__(self, name, value, schema)

    def _process_children(self):
        """
        Process an update to this setting's children
        """
        self._children = {}

        # If there is an item list, then we are dealing with a strict definition
        items = self._schema.get("items")
        if items:
            for sub_key, value_schema in items.iteritems():
                value_name = "%s[\"%s\"]" % (self._name, sub_key)
                sub_value = self._value[sub_key]
                self._children[sub_key] = create_plugin_setting(value_name, sub_value, value_schema)

        # Else just process the user-defined items
        else:
            value_schema = self._schema.get("values", {})
            for sub_key, sub_value in self._value.iteritems():
                value_name = "%s.%s" % (self._name, sub_key)
                self._children[sub_key] = create_plugin_setting(value_name, sub_value, value_schema)

    def __getitem__(self, key):
        return self._children[key]

    def __iter__(self):
        return iter(self._children)

    def __len__(self):
        return len(self._children)


def get_setting_for_context(settings_key, context=None, plugin_schema={}, validate=False):
    """
    """
    # the current bundle (the publisher instance)
    app = sgtk.platform.current_bundle()

    # Set the context if not specified
    context = context or app.context

    logger.debug("Finding plugin setting '%s' for context: %s" % (settings_key, context))

    if context == app.context:
        # if the context matches the bundle, we don't need to do any extra
        # work since the settings are already accessible via our app instance
        app_obj = app
    else:
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

        # Create a new app instance from the new env / context
        app_obj = sgtk.platform.application.get_application(
                app.engine,
                new_descriptor.get_path(),
                new_descriptor,
                new_settings,
                new_app,
                new_env,
                context)

    # Inject the plugin's schema for proper settings resolution
    schema = copy.deepcopy(app_obj.descriptor.configuration_schema)
    dict_merge(schema, plugin_schema)

    # Resolve the setting value, this also implicitly validates the value
    resolved_setting = sgtk.platform.bundle.resolve_setting_value(
                          app_obj.sgtk,
                          app_obj.engine.name,
                          schema[settings_key],
                          app_obj.settings,
                          settings_key,
                          None,
                          bundle=app_obj,
                          validate=validate
                      )
    if not resolved_setting:
        logger.debug("Could not resolve setting '%s' for context: %s" % (settings_key, context))

    return resolved_setting

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
