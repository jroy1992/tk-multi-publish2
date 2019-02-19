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
import pprint
import re
import mari
import sgtk
from sgtk import TankError
from sgtk.util.filesystem import ensure_folder_exists

HookBaseClass = sgtk.get_hook_baseclass()


MARI_TEXTURES_ITEM_TYPE_SETTINGS = {
    "mari.channel": {
        "publish_type": "UDIM Image",
        "publish_name_template": None,
        "publish_path_template": None
    },
    "mari.texture": {
        "publish_type": "UDIM Image",
        "publish_name_template": None,
        "publish_path_template": None
    }
}

class MariPublishTexturesPlugin(HookBaseClass):
    """
    Inherits from PublishFilesPlugin
    """
    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish Mari Textures"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        return """
        <p>This plugin publishes textures for the current Mari session to Shotgun.
        Additionally, any files will be exported to the path defined by this plugin's
        configured "Publish Path Template" setting.</p>
        """

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
        schema = super(MariPublishTexturesPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"] = ["mari.channel", "mari.texture"]
        schema["Item Type Settings"]["default_value"] = MARI_TEXTURES_ITEM_TYPE_SETTINGS
        return schema


    def validate(self, task_settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        geo_name = item.properties.mari_geo_name
        geo = mari.geo.find(geo_name)
        if not geo:
            error_msg = "Failed to find geometry in the project! Validation failed." % geo_name
            self.logger.error(error_msg)
            return False

        channel_name = item.properties.mari_channel_name
        channel = geo.findChannel(channel_name)
        if not channel:
            error_msg = "Failed to find channel on geometry! Validation failed." % channel_name
            self.logger.error(error_msg)
            return False

        layer_name = item.properties.get("mari_layer_name")
        if layer_name:
            layer = channel.findLayer(layer_name)
            if not layer:
                error_msg = "Failed to find layer for channel: %s Validation failed." % layer_name
                self.logger.error(error_msg)
                return False

        return super(MariPublishTexturesPlugin, self).validate(task_settings, item)


    def publish_files(self, task_settings, item, publish_path):
        """
        Overrides the inherited method to export out session items to the publish_path location.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :param publish_path: The output path to publish files to
        """
        publisher = self.parent

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(publish_path)

        try:
            # ensure the publish folder exists:
            publish_folder = os.path.dirname(path)
            ensure_folder_exists(publish_folder)

            geo_name        = item.properties.mari_geo_name
            channel_name    = item.properties.mari_channel_name
            layer_name      = item.properties.get("mari_layer_name")

            geo = mari.geo.find(geo_name)        
            channel = geo.findChannel(channel_name)

            if layer_name:
                layer = channel.findLayer(layer_name)
                layer.exportImages(path)

            else:
                # publish the entire channel, flattened
                layers = channel.layerList()
                if len(layers) == 1:
                    # only one layer so just publish it:
                    # Note - this works around an issue that was reported (#27945) where flattening a channel
                    # with only a single layer would cause Mari to crash - this bug was not reproducible by
                    # us but happened 100% for the client!
                    layer = layers[0]
                    layer.exportImages(path)

                elif len(layers) > 1:
                    # publish the flattened layer:
                    current_channel = geo.currentChannel()
                    current_channel.exportImagesFlattened(path)

                else:
                    self.logger.error("Channel '%s' doesn't appear to have any layers!" % channel.name())            

        except Exception as e:
            raise TankError("Failed to publish file for item '%s': %s" % (item.name, str(e)))

        self.logger.debug(
            "Published file for item '%s' to '%s'." % (item.name, path)
        )

        return [path]
