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
        if not super(MariPublishTexturesPlugin, self).validate(task_settings, item):
            return False

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

        all_udims = {patch.udim() for patch in geo.patchList()}
        selected_udims = {1001 + uv_index for uv_index in item.get_property("uv_index_list", [])}
        required_udims = all_udims - selected_udims

        return self._validate_udims_to_copy(task_settings, item, required_udims, selected_udims)

    def _validate_udims_to_copy(self, task_settings, item, required_udims, selected_udims):
        if not required_udims:
            # nothing to be copied, so everything is okay
            return True

        publisher = self.parent

        # find prev published version path
        udim_copy_path_list = item.get_property("udim_copy_path_list")

        if udim_copy_path_list is None:
            item.properties["udim_copy_path_list"] = []

            filters = [["entity", "is", item.context.entity],
                       ["task", "is", item.context.task],
                       ["name", "is", item.properties.publish_name]]
            order = [{'field_name': 'version_number', 'direction': 'desc'}]

            published_files = publisher.shotgun.find("PublishedFile",
                                                     filters,
                                                     fields=["version_number", "path"],
                                                     order=order,
                                                     limit=1)
            if not published_files:
                self.logger.error(
                    "No previous published files found and UDIM subset selected!",
                    extra={
                        "action_show_more_info": {
                            "label": "Show Error",
                            "tooltip": "Show more info",
                            "text": "No previous published files found for `{}` to copy UDIMs from. "
                                    "You need to publish all UDIMs atleast once for this item.\n"
                                    "Please select all or no UDIMs and hit reload to "
                                    "retry publishing".format(item.properties.publish_name)
                        }
                    }
                )
                return False

            latest_published_path = published_files[0]['path']['local_path_linux']

            self.logger.warning(
                "Some UDIMs to be exported and others copied!",
                extra = {
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show more info",
                        "text": "UDIMs to be exported from current session: {}\n"
                                "UDIMs to be copied: {}\n"
                                "They will be copied from {}".format(', '.join(map(str, selected_udims)),
                                                                     ', '.join(map(str, required_udims)),
                                                                     latest_published_path)
                    }
                }
            )

            for udim in required_udims:
                udim_path = publisher.util.get_path_for_frame(latest_published_path, frame_num=udim)
                if not os.path.exists(udim_path):
                    self.logger.error(
                        "UDIM {} not selected and not previously published!".format(udim),
                        extra={
                            "action_show_more_info": {
                                "label": "Show Error",
                                "tooltip": "Show more info",
                                "text": "Previous publish path not found on disk:\n{}\nPlease select "
                                        "UDIM {} to export it from this session.".format(udim_path, udim)
                            }
                        }
                    )
                    return False
                item.properties["udim_copy_path_list"].append(udim_path)

        return True

    def publish_files(self, task_settings, item, publish_path):
        """
        Overrides the inherited method to export out session items to the publish_path location.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :param publish_path: The output path to publish files to
        """

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
                layer.exportImages(path, UVIndexList=item.get_property("uv_index_list", []))

            else:
                # publish the entire channel, flattened
                layers = channel.layerList()
                if len(layers) == 1:
                    # only one layer so just publish it:
                    # Note - this works around an issue that was reported (#27945) where flattening a channel
                    # with only a single layer would cause Mari to crash - this bug was not reproducible by
                    # us but happened 100% for the client!
                    layer = layers[0]
                    layer.exportImages(path, UVIndexList=item.get_property("uv_index_list", []))

                elif len(layers) > 1:
                    # publish the flattened layer:
                    channel.exportImagesFlattened(path, UVIndexList=item.get_property("uv_index_list", []))

                else:
                    self.logger.error("Channel '%s' doesn't appear to have any layers!" % channel.name())

            # after export is completed, try to copy over the udims from previous publish
            self._copy_udims(task_settings, item, publish_path)

        except Exception as e:
            raise TankError("Failed to publish file for item '%s': %s" % (item.name, str(e)))

        self.logger.debug(
            "Published file for item '%s' to '%s'." % (item.name, path)
        )

        return [path]

    def _copy_udims(self, task_settings, item, publish_path):
        # this property should be created in validate
        udim_copy_path_list = item.get_property("udim_copy_path_list")

        # if empty, assume all udims were exported and nothing needs to be copied
        if not udim_copy_path_list:
            return True

        publisher = self.parent
        seal_files = item.properties.get("seal_files", False)

        return publisher.util.copy_files(udim_copy_path_list, publish_path, seal_files=seal_files,
                                         is_sequence=True)
