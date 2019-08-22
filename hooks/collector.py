# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import copy
import datetime
import urllib
import sgtk
from sgtk.templatekey import SequenceKey

HookBaseClass = sgtk.get_hook_baseclass()


class CollectorPlugin(HookBaseClass):
    """
    A basic collector that other collectors can derive common functionality from.

    """

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
        schema = super(CollectorPlugin, self).settings_schema
        schema["Item Types"]["values"]["items"] = {
            "icon_path": {
                "type": "config_path",
                "description": ""
            },
            "type_display": {
                "type": "str",
                "description": ""
            }
        }
        return schema


    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current scene open in a DCC and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        # default implementation does not do anything
        return []


    def process_file(self, settings, parent_item, path):
        """
        Analyzes the given file and creates one or more items
        to represent it.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        :param path: Path to analyze

        :returns: The main item that was created, or None if no item was created
            for the supplied path
        """
        # default implementation does not do anything
        return []


    def on_context_changed(self, settings, item):
        """
        Callback to update the item on context changes.

        :param dict settings: Configured settings for this collector
        :param item: The Item instance
        """
        # Set the item's fields property
        item.properties.fields = self._resolve_item_fields(settings, item)


    ############################################################################
    # protected helper methods

    def _add_item(self, settings, parent_item, item_name, item_type, context=None, properties=None):
        """
        Creates a generic item

        :param dict settings: Configured settings for this collector
        :param parent_item: parent item instance
        :param item_name: The name of the item instance
        :param item_type: The type of the item instance
        :param context: The :class:`sgtk.Context` to set for the item
        :param properties: The dict of initial properties for the item

        :returns: The item that was created and its item_info dictionary
        """
        publisher = self.parent

        # Get this item's info from the settings object
        item_info = self._get_item_type_info(settings, item_type)

        type_display = item_info["type_display"]
        icon_path    = item_info["icon_path"]

        # create and populate the item
        item = parent_item.create_item(
            item_type,
            type_display,
            item_name,
            context=context,
            properties=properties
        )

        self.logger.debug("Added %s of type %s" % (item_name, item_type))

        # construct a full path to the icon given the name defined above
        icon_path = publisher.expand_path(icon_path)

        # Set the icon path
        item.set_icon_from_path(icon_path)

        return item


    def _get_item_type_info(self, settings, item_type):
        """
        Return the dictionary corresponding to this item's 'Item Types' settings.

        :param dict settings: Configured settings for this collector
        :param item_type: The type of Item to identify info for

        :return: A dictionary of information about the item to create::

            # item_type = "mari.session"

            {
                "type_display": "Mari Session",
                "icon_path": "/path/to/some/icons/folder/mari.png",
            }
        """
        # default values used if no specific type can be determined
        default_item_info = {
            'type_display' : 'Item',
            'icon_path' : '{self}/hooks/icons/file.png'
        }

        item_types = copy.deepcopy(settings["Item Types"].value)
        return item_types.get(item_type, default_item_info)


    def __get_parent_version_number_r(self, item):
        """
        Recurse up item hierarchy to determine version number
        """
        publisher = self.parent

        # If this isn't the root item...
        if not item.is_root:
            # Try and get the version from the parent's fields
            if "fields" in item.parent.properties:
                version = item.parent.properties.fields.get("version")
                if version:
                    return version

            # Next try and get the version from the parent's path
            path = item.parent.properties.get("path")
            if path:
                version = publisher.util.get_version_number(path)
                if version:
                    return version

            # Next try and get it from the parent's parent
            version = self.__get_parent_version_number_r(item.parent)
            if version:
                return version

        # Couldn't determine version number
        return None


    def __get_name_field_r(self, item):
        """
        Recurse up item hierarchy to determine the name field
        """
        if not item:
            return None

        if "fields" in item.properties:
            name_field = item.properties.fields.get("name")
            if name_field:
                return name_field

        if item.parent:
            return self.__get_name_field_r(item.parent)

        return None


    def _resolve_item_fields(self, settings, item):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        publisher = self.parent

        fields = {}

        # use %V - full view printout as default for the eye field
        fields["eye"] = "%V"

        # add in date values for YYYY, MM, DD
        today = datetime.date.today()
        fields["YYYY"] = today.year
        fields["MM"] = today.month
        fields["DD"] = today.day

        # Try to set the name field
        # First attempt to get it from the parent item
        name_field = self.__get_name_field_r(item.parent)
        if name_field:
            fields["name"] = name_field

        # Else attempt to use a sanitized task name
        elif item.context.task:
            name_field = item.context.task["name"]
            fields["name"] = urllib.quote(name_field.replace(" ", "_").lower(), safe='')

        # if item is not a sequence, set all sequence keys explicitly to None
        if not item.get_property("is_sequence"):
            for key in self.sgtk.template_keys.values():
                if isinstance(key, SequenceKey):
                    fields[key.name] = None

        return fields
