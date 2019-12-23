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

import mari
import sgtk
from sgtk import TankError
from sgtk.util.filesystem import ensure_folder_exists, freeze_permissions

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

        if item.get_property("uv_index_list") is None:
            return True
        else:
            all_udims = {patch.udim() for patch in geo.patchList()}
            udims_to_export = {1001 + uv_index for uv_index in item.get_property("uv_index_list")}
            udims_to_be_reused = all_udims - udims_to_export

            return self._validate_udims_to_reuse(task_settings, item, udims_to_be_reused, udims_to_export)

    def _validate_udims_to_reuse(self, task_settings, item, udims_to_be_reused, udims_to_export):
        if not udims_to_be_reused:
            # nothing to be reused, so everything is okay
            return True

        publisher = self.parent

        # cache the previous published version path
        cached_reuse_publish_path = item.get_property("cached_reuse_publish_path")

        if cached_reuse_publish_path is None:
            filters = [["entity", "is", item.context.entity],
                       ["task", "is", item.context.task],
                       ["name", "is", item.get_property("publish_name")]]
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
                            "text": "No previous published files found for `{}` to reuse UDIMs from. "
                                    "You need to publish all UDIMs atleast once for this item.\n"
                                    "Please select all or no UDIMs and hit reload to "
                                    "retry publishing".format(item.get_property("publish_name"))
                        }
                    }
                )
                return False

            cached_reuse_publish_path = published_files[0]['path']['local_path_linux']
            item.local_properties["cached_reuse_publish_path"] = cached_reuse_publish_path

        # find prev published version path
        self.logger.warning(
            "Some UDIMs will be reused from previous publish!",
            extra={
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": "UDIMs to be exported from current session: {}\n"
                            "UDIMs to be reused: {}\n"
                            "They will be reused from {}".format(', '.join(map(str, udims_to_export)),
                                                                           ', '.join(map(str, udims_to_be_reused)),
                                                                           cached_reuse_publish_path)
                }
            }
        )

        udim_files = publisher.util.get_sequence_path_files(cached_reuse_publish_path)
        available_udims = {int(publisher.util.get_frame_number(path)) for path in udim_files}
        non_available_udims = udims_to_be_reused - available_udims

        if non_available_udims:
            self.logger.error(
                "Some UDIMs not selected and not previously published!",
                extra={
                    "action_show_more_info": {
                        "label": "Show Error",
                        "tooltip": "Show more info",
                        "text": "Previous publish path not found on disk:\n{}\nfor UDIMs {}.\n"
                                "Please select them to export from this session.".format(cached_reuse_publish_path,
                                                                                         non_available_udims)
                    }
                }
            )
            return False
        else:
            # subtract the udims to be exported from the reuse path list
            # otherwise exported udims will be overwritten by reused paths
            reuse_path_list = [path for path in udim_files if
                               int(publisher.util.get_frame_number(path)) not in udims_to_export]
            item.local_properties["udim_reuse_path_list"] = reuse_path_list

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

            uv_index_list = item.get_property("uv_index_list")
            if uv_index_list != []:
                if layer_name:
                    layer = channel.findLayer(layer_name)
                    layer.exportImages(path, UVIndexList=uv_index_list or [])

                else:
                    # publish the entire channel, flattened
                    layers = channel.layerList()
                    if len(layers) == 1:
                        # only one layer so just publish it:
                        # Note - this works around an issue that was reported (#27945) where flattening a channel
                        # with only a single layer would cause Mari to crash - this bug was not reproducible by
                        # us but happened 100% for the client!
                        layer = layers[0]
                        layer.exportImages(path, UVIndexList=uv_index_list or [])
                        self._freeze_udim_permissions(path)

                    elif len(layers) > 1:
                        # publish the flattened layer:
                        channel.exportImagesFlattened(path, UVIndexList=uv_index_list or [])
                        self._freeze_udim_permissions(path)

                    else:
                        self.logger.error("Channel '%s' doesn't appear to have any layers!" % channel.name())

            # after export is completed, try to reuse over the udims from previous publish
            self._reuse_udims(task_settings, item, publish_path)

        except Exception as e:
            raise TankError("Failed to publish file for item '%s': %s" % (item.name, str(e)))

        self.logger.debug(
            "Published file for item '%s' to '%s'." % (item.name, path)
        )

        # TODO: return expanded list
        return [path]

    def _reuse_udims(self, task_settings, item, publish_path):
        # this property should be created in validate
        udim_reuse_path_list = item.get_property("udim_reuse_path_list")

        # if empty, assume all udims were exported and nothing needs to be reused
        if not udim_reuse_path_list:
            return True

        publisher = self.parent
        seal_files = item.properties.get("seal_files", False)


        if task_settings["Copy Files"].value:
            return publisher.util.copy_files(udim_reuse_path_list, publish_path,
                                             seal_files=seal_files, is_sequence=True)
        else:
            return publisher.util.hardlink_files(udim_reuse_path_list, publish_path, is_sequence=True)


    def _freeze_udim_permissions(self, path):
        publisher = self.parent
        udim_files = publisher.util.get_sequence_path_files(path)
        for file in udim_files:
            freeze_permissions(file)

