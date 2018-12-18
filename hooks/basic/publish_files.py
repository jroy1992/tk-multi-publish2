# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import copy
import glob
import pprint
import traceback

import sgtk
from sgtk import TankError

HookBaseClass = sgtk.get_hook_baseclass()


DEFAULT_ITEM_TYPE_SETTINGS = {
    "file.alembic": {
        "publish_type": "Alembic Cache",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.3dsmax": {
        "publish_type": "3dsmax Scene",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.nukestudio": {
        "publish_type": "NukeStudio Project",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.houdini": {
        "publish_type": "Houdini Scene",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.maya": {
        "publish_type": "Maya Scene",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.motionbuilder": {
        "publish_type": "Motion Builder FBX",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.nuke": {
        "publish_type": "Nuke Script",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.photoshop": {
        "publish_type": "Photoshop Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.render.sequence": {
        "publish_type": "Rendered Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.texture": {
        "publish_type": "Texture Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.image": {
        "publish_type": "Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "file.video": {
        "publish_type": "Movie",
        "publish_name_template": None,
        "publish_path_template": None
    },
}

class FilePublishPlugin(HookBaseClass):
    """
    Plugin for creating generic publishes in Shotgun.

    This plugin is typically configured to act upon files that are dragged and
    dropped into the publisher UI. It can also be used as a base class for
    other file-based publish plugins as it contains standard operations for
    validating and registering publishes with Shotgun.

    Once attached to a publish item, the plugin will key off of properties that
    drive how the item is published.

    The ``path`` property, set on the item, is the only required property as it
    informs the plugin where the file to publish lives on disk.

    The following properties can be set on the item via the collector or by
    subclasses prior to calling methods on the base class::

        ``path`` - The path to the file to be published.

        ``sequence_paths`` - If set, implies the "path" property represents a
            sequence of files (typically using a frame identifier such as %04d).
            This property should be a list of files on disk matching the "path".

        ``is_sequence`` - A boolean defining whether or not this item is a sequence of files.

    The following properties can also be set by a subclass of this plugin via
    :meth:`Item.properties` or :meth:`Item.local_properties`.

        publish_type - Shotgun PublishedFile instance type.

        publish_name - Shotgun PublishedFile instance name.

        publish_version - Shotgun PublishedFile instance version.

        publish_path - The location on disk the publish is copied to.

        sg_publish_data_list - A list of dictionaries of publish information returned from
            the tk-core register_publish method.

    """

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish File(s) to Shotgun"

    @property
    def settings_schema(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default_value": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts
        as part of its environment configuration.
        """
        schema = super(FilePublishPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"].append("file.*")
        schema["Item Type Settings"]["default_value"].update(DEFAULT_ITEM_TYPE_SETTINGS)
        return schema


    ############################################################################
    # standard publish plugin methods

    def accept(self, task_settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        # Run the parent acceptance method
        accept_data = super(FilePublishPlugin, self).accept(task_settings, item)
        if not accept_data.get("accepted"):
            return accept_data

        if item.type.startswith("file."):
            path = item.properties.get("path")
            if not path:
                msg = "'path' property is not set for item: %s" % item.name
                accept_data["extra_info"] = {
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show more info",
                        "text": msg
                    }
                }
                accept_data["accepted"] = False

        # return the accepted data
        return accept_data


    def validate(self, task_settings, item):
        """
        Validates the given item to check that it is ok to publish.

        Returns a boolean to indicate validity.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: True if item is valid, False otherwise.
        """

        # ---- ensure that work file(s) exist on disk to be published
        if item.type.startswith("file."):
            if item.properties.is_sequence:
                if not item.properties.sequence_paths:
                    self.logger.warning("File sequence does not exist: %s" % item.properties.path)
                    return False
            else:
                if not os.path.exists(item.properties.path):
                    self.logger.warning("File does not exist: %s" % item.properties.path)
                    return False

        return super(FilePublishPlugin, self).validate(task_settings, item)
