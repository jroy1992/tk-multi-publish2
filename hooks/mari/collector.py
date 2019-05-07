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
import tempfile
import urllib
import uuid

import mari
import sgtk
from sgtk import TankError
from sgtk.platform.qt import QtGui

HookBaseClass = sgtk.get_hook_baseclass()


# This is a dictionary of file type info that allows the basic collector to
# identify common production file types and associate them with a display name,
# item type, and config icon.
MARI_SESSION_ITEM_TYPES = {
    "mari.session": {
        "icon_path": "{self}/hooks/icons/mari.png",
        "type_display": "Mari Session"
    },
    "mari.channel": {
        "icon_path": "{self}/hooks/icons/mari_channel.png",
        "type_display": "Channel"
    },
    "mari.layers": {
        "icon_path": "{self}/hooks/icons/mari_layer.png",
        "type_display": "Unflattened layers for the channel"
    },
    "mari.texture": {
        "icon_path": "{self}/hooks/icons/texture.png",
        "type_display": "Layer"    
    },
}


class MariSessionCollector(HookBaseClass):
    """
    Collector that operates on the mari session. Should inherit from the basic
    collector hook.
    """
    def __init__(self, parent, **kwargs):
        """
        Construction
        """
        # call base init
        super(MariSessionCollector, self).__init__(parent, **kwargs)

        # cache the projectmanager app
        self.__projectmanager_app = self.parent.engine.apps.get("tk-mari-projectmanager")


    @property
    def settings_schema(self):
        """
        Dictionary defining the settings that this collector expects to receive
        through the settings parameter in the process_current_session and
        process_file methods.

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
        schema = super(MariSessionCollector, self).settings_schema
        schema["Item Types"]["default_value"].update(MARI_SESSION_ITEM_TYPES)
        schema["Work File Templates"] = {
            "type": "list",
            "values": {
                "type": "template",
                "description": "",
                "fields": "context, *"
            },
            "default_value": [],
            "allows_empty": True,
            "description": "A list of templates to use to search for work files."
        }
        schema["Collect Layers"] = {
            "type": "bool",
            "default_value": False,
            "allows_empty": True,
            "description": "Indicates whether layers should be collected for individual export."
        }
        return schema


    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current session open in Mari and parents a subtree of
        items under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        items = []

        if not mari.projects.current():
            self.logger.warning("You must be in an open Mari project. No items collected!")
            return items

        if not self.__projectmanager_app:
            self.logger.error("Unable to process items under '%s' without "
                    "the tk-mari-projectmanager app!" % parent_item.name)
            return items

        # create an item representing the current mari session
        session_item = self.collect_current_mari_session(settings, parent_item)
        if session_item:
            items.append(session_item)

        # collect any items for flattened channels and individual layers
        items.extend(self.collect_texture_elements(settings, session_item))

        # if we have work path templates, collect matching files to publish
        for work_template in settings["Work File Templates"].value:
            items.extend(self.collect_work_files(settings, session_item, work_template))

        # Return the list of items
        return items


    def collect_current_mari_session(self, settings, parent_item):
        """
        Analyzes the current session open in Mari and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        # Define the item's properties
        properties = {}

        # Add the current project as a property
        properties["project"] = mari.projects.current()

        session_item = self._add_item(settings,
                                      parent_item,
                                      "Current Mari Session",
                                      "mari.session",
                                      parent_item.context,
                                      properties)

        self.logger.info("Collected item: %s" % session_item.name)
        return session_item


    def collect_texture_elements(self, settings, parent_item):
        """
        Creates items for both the flattened channels as well as the individual layers

        :param dict settings: Configured settings for this collector
        :param parent_item: Parent Item instance
        :return:
        """
        items = []
        collect_layers = settings["Collect Layers"].value
        thumbnail = self._extract_mari_thumbnail()

        # TODO: should be replaced by create_settings_widget?
        geo_udim_selection = {}

        # Look for all layers for all channels on all geometry.  Create items for both
        # the flattened channel as well as the individual layers
        for geo in mari.geo.list():
            geo_name = geo.name()

            # skip any non-sgtk compliant geometries
            geo_sg_metadata = self.parent.engine.get_shotgun_info(geo)
            if not geo_sg_metadata:
                self.logger.warning("{} is not an sgtk geometry. Ignoring it.".format(geo_name))
                continue

            uv_index_list = []
            selected_patches = geo.selectedPatches()
            if selected_patches:
                uv_index_list = [patch.uvIndex() for patch in selected_patches]
                # TODO: should be replaced by create_settings_widget?
                geo_udim_selection[geo_name] = [patch.udim() for patch in selected_patches]

            for channel in geo.channelList():
                channel_name = channel.name()

                # skip channels with invalid names
                channel_template_key = self.sgtk.template_keys["channel"]
                if not channel_template_key.validate(channel_name):
                    self.logger.warning("Channel '%s' does not conform to sgtk naming. "
                                        "The channel will not be collected" % channel_name)
                    continue

                # find all collected layers:
                found_layers = self._find_layers_r(channel.layerList())
                if not found_layers:
                    # no layers to publish!
                    self.logger.warning("Channel '%s' has no layers. The channel will not be collected" % channel_name)
                    continue

                # Define the item's properties
                properties = {}

                # Add the geo and channel names as properties
                properties["mari_geo_name"] = geo_name
                properties["mari_channel_name"] = channel_name

                # Add selected uv_index_list
                properties["uv_index_list"] = uv_index_list

                # textures should always contain UDIM or tag <UDIM>
                properties["is_sequence"] = True

                # add item for whole flattened channel:
                item_name = "%s, %s" % (channel_name, geo_name)
                channel_item = self._add_item(settings,
                                              parent_item,
                                              item_name,
                                              "mari.channel",
                                              parent_item.context,
                                              properties)

                channel_item.set_thumbnail_from_path(thumbnail)
                channel_item.thumbnail_enabled = True

                self.logger.info("Collected item: %s" % channel_item.name)
                items.append(channel_item)
                
                if collect_layers and len(found_layers) > 1:
                    items.extend(self._add_layers_to_channel_item(settings,
                                                                  channel_item,
                                                                  found_layers,
                                                                  thumbnail))

        # TODO: should be replaced by create_settings_widget?
        if geo_udim_selection:
            udim_selection_str = "\n".join(["\t{}: {}".format(geo, udims)
                                            for geo, udims in geo_udim_selection.items()])
            self.logger.warning(
                "Only selected UDIMs will be published!",
                extra={
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show more info",
                        "text": "UDIMs to be exported from current session:\n{}\n"
                                "Any remaining will be copied from the previous version "
                                "that was published.".format(udim_selection_str)
                    }
                }
            )

            message_str = "UDIMs selected per geometry:\n"
            message_str += udim_selection_str
            message_str += "\n\nOnly selected UDIMs will be exported (rest copied from previous version). " \
                           "If you want to export all, please deselect any patches in the geo " \
                           "and hit the refresh button at the bottom."

            QtGui.QMessageBox.information(None, "UDIMs selected for export", message_str)

        return items

    def _add_layers_to_channel_item(self, settings, channel_item, layer_list, thumbnail):
        """
        Create items for each layer in the given list of layers
        and parent them under the given channel item

        :param settings:        Configured settings for this collector
        :param channel_item:    Channel item to parent created items under
        :param layer_list:      List of layers found within this channel
        :param thumbnail:       Path to thumbnail to add to each layer item

        :return:                List of items created
        """
        items = []
        layers_item = self._add_item(settings,
                                     channel_item,
                                     "Texture Channel Layers",
                                     "mari.layers")
        items.append(layers_item)

        # add item for each collected layer:
        found_layer_names = set()
        for layer in layer_list:

            layer_name = layer.name()

            # for now, duplicate layer names aren't allowed!
            if layer_name in found_layer_names:
                # we might want to handle this one day...
                self.logger.warning(
                    "Duplicate layer name found: %s. Layer will not be exported" % layer_name)
                continue

            # skip layers with invalid names
            layer_template_key = self.sgtk.template_keys["layer"]
            if not layer_template_key.validate(layer_name):
                self.logger.warning("Layer '%s' does not conform to sgtk naming. "
                                    "The layer will not be collected" % layer_name)
                continue


            found_layer_names.add(layer_name)

            # Define the item's properties
            layer_properties = copy.deepcopy(channel_item.properties)

            # Add the layer name as a property as well
            layer_properties["mari_layer_name"] = layer_name

            item_name = "%s (%s), %s" % (layer_properties["mari_channel_name"],
                                         layer_name,
                                         layer_properties["mari_geo_name"])
            layer_item = self._add_item(settings,
                                        layers_item,
                                        item_name,
                                        "mari.texture",
                                        channel_item.context,
                                        layer_properties)

            layer_item.set_thumbnail_from_path(thumbnail)
            layer_item.thumbnail_enabled = True

            self.logger.info("Collected item: %s" % layer_item.name)
            items.append(layer_item)

        return items


    def _find_layers_r(self, layers):
        """
        Find all layers within the specified list of layers.  This will return
        all layers that are either paintable or procedural and traverse any layer groups
        to find all grouped layers to be collected
        :param layers:  The list of layers to inspect
        :returns:       A list of all collected layers
        """
        collected_layers = []
        for layer in layers:
            # Note, only paintable or procedural layers are exportable from Mari - all
            # other layer types are only used within Mari.
            if layer.isPaintableLayer() or layer.isProceduralLayer():
                # these are the only types of layers that can be collected
                collected_layers.append(layer)
            elif layer.isGroupLayer():
                # recurse over all layers in the group looking for exportable layers:
                grouped_layers = self._find_layers_r(layer.layerStack().layerList())
                collected_layers.extend(grouped_layers or [])
    
        return collected_layers


    def _extract_mari_thumbnail(self):
        """
        Render a thumbnail for the current canvas in Mari
        
        :returns:   The path to the thumbnail on disk
        """
        if not mari.projects.current():
            return
        
        canvas = mari.canvases.current()
        if not canvas:
            return
        
        # calculate the maximum size to capture:
        MAX_THUMB_SIZE = 512
        sz = canvas.size()
        thumb_width = sz.width()
        thumb_height = sz.height()
        max_sz = max(thumb_width, sz.height())
    
        if max_sz > MAX_THUMB_SIZE:
            scale = min(float(MAX_THUMB_SIZE)/float(max_sz), 1.0)
            thumb_width = max(min(int(thumb_width * scale), thumb_width), 1)
            thumb_height = max(min(int(thumb_height * scale), thumb_height), 1)
    
        # disable the HUD:
        hud_enabled = canvas.getDisplayProperty("HUD/RenderHud")
        if hud_enabled:
            # Note - this doesn't seem to work when capturing an image!
            canvas.setDisplayProperty("HUD/RenderHud", False)

        # render the thumbnail:
        thumb = None
        try:    
            thumb = canvas.captureImage(thumb_width, thumb_height)
        except:
            pass
        
        # reset the HUD
        if hud_enabled:
            canvas.setDisplayProperty("HUD/RenderHud", True)
        
        if thumb:
            # save the thumbnail
            jpg_thumb_path = os.path.join(tempfile.gettempdir(), "sgtk_thumb_%s.jpg" % uuid.uuid4().hex)
            thumb.save(jpg_thumb_path)
        
        return jpg_thumb_path


    def collect_work_files(self, settings, parent_item, work_template):
        """
        Creates items for files matching the work path template
        """
        items = []
        try:
            work_paths = self._get_work_paths(parent_item, work_template)
            for work_path in work_paths:
                item = self._collect_file(settings, parent_item, work_path)
                if not item:
                    continue

				# Track the current work template being processed
                item.properties.work_path_template = work_template

                # Add the item to the list
                items.append(item)

        except Exception as e:
            self.logger.warning("%s. Skipping..." % str(e))

        return items


    def _get_work_paths(self, parent_item, work_path_template):
        """
        Get paths matching the work path template using the supplied item's fields.

        :param parent_item: The item to determine the work path for
        :param work_path_template: The template string to resolve

        :return: A list of paths matching the resolved work path template for
            the supplied item

        Extracts the work path via the configured work templates
        if possible.
        """

        publisher = self.parent

        # Start with the item's fields, minus extension
        fields = copy.deepcopy(parent_item.properties.get("fields", {}))
        fields.pop("extension", None)

        work_tmpl = publisher.get_template_by_name(work_path_template)
        if not work_tmpl:
            # this template was not found in the template config!
            raise TankError("The Template '%s' does not exist!" % work_path_template)

        # First get the fields from the context
        try:
            fields.update(parent_item.context.as_template_fields(work_tmpl))
        except TankError as e:
            self.logger.warning(
                "Unable to get context fields for work_path_template.")

        # Get the paths from the template using the known fields
        self.logger.info(
            "Searching for file(s) matching: '%s'" % work_path_template,
            extra={
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": "Template: %s\nFields: %s" % (work_tmpl, fields)
                }
            }
        )
        return self.sgtk.abstract_paths_from_template(work_tmpl,
                                                      fields,
                                                      skip_missing_optional_keys=True)


    def _resolve_item_fields(self, settings, item):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        # First run the parent resolve method
        fields = super(MariSessionCollector, self)._resolve_item_fields(settings, item)

        if item.type == "mari.session":
            # Parse the project name to get some fields...
            project_name = item.properties.project.info().name()
            project_name_template = self.__projectmanager_app.get_setting("template_new_project_name")
            if project_name_template:
                fields.update(self._get_template_fields_from_path(item, project_name_template, project_name))

            # See if we have a stored version number for the project
            proj_version = self.parent.engine.get_project_version(item.properties.project)
            if proj_version:
                fields["version"] = proj_version

            # If we don't, no problem, just assume we're at v1
            else:
                fields["version"] = 1

        elif item.type in ("mari.channel", "mari.texture"):
            geo_name     = item.properties.mari_geo_name
            channel_name = item.properties.mari_channel_name
            layer_name   = item.properties.get("mari_layer_name")

            geo = mari.geo.find(geo_name)
            channel = geo.findChannel(channel_name)

            # For the sake of brevity, only set the node name if the geo entity
            # is different than the context entity, or there are more than one geos
            geo_entity = self.parent.engine.get_shotgun_info(geo).get("entity")
            if ((geo_entity and geo_entity.get("id") != item.context.entity["id"]) or
                len(mari.geo.list()) > 1):
                fields["node"] = geo_entity["name"]

            fields["channel"] = channel_name
            fields["layer"] = layer_name
            fields["UDIM"] = "FORMAT: $UDIM"

        return fields
