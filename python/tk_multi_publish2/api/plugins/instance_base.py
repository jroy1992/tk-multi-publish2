# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import traceback
import sgtk

logger = sgtk.platform.get_logger(__name__)


class PluginInstanceBase(object):
    """
    A base class for functionality common to plugin hooks (collectors and
    publish plugins).

    Each object reflects an instance in the app configuration.
    """

    def __init__(self, path, context, publish_logger):
        """
        Initialize a plugin instance.

        :param path: Path to the collector hook
        :param context: The Context to use to resolve this plugin's settings
        :param publish_logger: a logger object that will be used by the hook
        """

        super(PluginInstanceBase, self).__init__()

        if not publish_logger:
            publish_logger = logger

        self._logger = publish_logger

        # all plugins need a hook and a name
        self._path = path
        self._context = context

        self._settings = {}

        # create an instance of the hook
        self._hook_instance = self._create_hook_instance(self._path)

        # kick things off
        self._validate_and_resolve_config()

    def _create_hook_instance(self, path):
        """
        Create the plugin's hook instance. Subclasses can reimplement for more
        sophisticated hook instantiation.

        :param str path: The path to the hook file.
        :return: A hook instance
        """
        bundle = sgtk.platform.current_bundle()
        hook = bundle.create_hook_instance(
            path,
            base_class=bundle.base_hooks.PluginBase,
            plugin=self
        )
        hook.id = path
        return hook

    def __repr__(self):
        """
        String representation
        """
        return "<%s: %s>" % (self.__class__.__name__, self._path)

    def _validate_and_resolve_config(self):
        """
        Init helper method.

        Validates plugin settings and creates a dictionary of Setting objects
        that can be accessed from the settings property.
        """
        try:
            self._settings_schema = self._hook_instance.settings_schema
        except NotImplementedError as e:
            # property not defined by the hook
            self._logger.error("No settings_schema defined by hook: %s" % self)
            self._settings_schema = {}

        # Settings schema will be in the form:
        # "setting_a": {
        #     "type": "int",
        #     "default": 5,
        #     "description": "foo bar baz"
        # },

        # Get the resolved settings for the plugin from the specified context
        try:
            self._settings = self.get_plugin_settings(self._context)
        except Exception as e:
            error_msg = traceback.format_exc()
            self._logger.error(
                "Error validating settings for plugin %s in context '%s': %s" %
                (self, self._context, error_msg)
            )

    @property
    def context(self):
        """
        The context for this plugin instance.
        """
        return self._context

    @property
    def logger(self):
        """
        The logger used by this plugin instance.
        """
        return self._logger

    @logger.setter
    def logger(self, new_logger):
        # set the plugin's logger instance
        self._logger = new_logger

    @property
    def path(self):
        """The path to this plugin as specified in the pipeline config."""
        return self._path

    @property
    def settings(self):
        """
        A dict of resolved raw settings given the current state
        """
        return self._settings

    @property
    def settings_schema(self):
        """
        A dictionary of settings schema data as originally specified for this plugin
        instance in the pipeline configuration.
        """
        return self._settings_schema

    def get_plugin_settings(self, context=None):
        """
        Find and resolve settings for the plugin in the specified context

        :param context: Context in which to look for settings.

        :returns: The plugin settings for the given context or None.
        """
        raise NotImplementedError
