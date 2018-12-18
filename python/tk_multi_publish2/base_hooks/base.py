# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

class PluginBase(HookBaseClass):
    """
    Base Plugin class.
    """
    def __init__(self, parent, plugin=None, **kwargs):
        """
        Construction
        """
        # call base init
        super(PluginBase, self).__init__(parent, **kwargs)

        # initialize plugin
        self.__plugin = plugin

    @property
    def id(self):
        """
        Unique string identifying this plugin.
        """
        return self._id

    @id.setter
    def id(self, new_id):
        """
        Allows to set the unique string identifying this plugin.
        """
        self._id = new_id

    @property
    def settings_schema(self):
        """
        Dictionary defining the settings that this plugin expects to recieve
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default_value": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """
        raise NotImplementedError

    @property
    def plugin(self):
        """
        A reference to the parent Plugin class that instantiated this hook.
        """
        return self.__plugin
