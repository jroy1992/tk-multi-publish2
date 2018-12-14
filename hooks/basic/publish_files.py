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

class PublishFilesPlugin(HookBaseClass):
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

        publish_dependencies - A list of files to include as dependencies when
            registering the publish. If the item's parent has been published,
            it's path will be appended to this list.

        Task settings
        -------------------

        publish_type - If set in the plugin settings dictionary, will be
            supplied to SG as the publish type when registering "path" as a new
            publish. This is required.

        publish_name_template - If set in the plugin settings dictionary, will be
            supplied to SG as the publish name when registering the new publish.
            If not available, will fall back to the ``path_info`` hook logic.

        publish_path_template - If set in the plugin settings dictionary, used to
            determine where "path" should be copied prior to publishing. If
            not specified, "path" will be published in place.

    The following properties can also be set by a subclass of this plugin via
    :meth:`Item.properties` or :meth:`Item.local_properties`.

        publish_type - Shotgun PublishedFile instance type.

        publish_name - Shotgun PublishedFile instance name.

        publish_version - Shotgun PublishedFile instance version.

        publish_path - The location on disk the publish is copied to.

        sg_publish_data_list - A list of The dictionary of publish information returned from
            the tk-core register_publish method.

    """

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """
        # look for icon one level up from this hook's folder in "icons" folder
        return self.parent.expand_path("{self}/hooks/icons/publish.png")

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish File(s)"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        loader_url = "https://support.shotgunsoftware.com/hc/en-us/articles/219033078"

        return """
        Publishes the file to the specified <b>Publish Path</b> location and
        creates a <b>PublishedFile</b> entity in Shotgun, which will include a
        reference to the file's published path on disk. Other users will be able
        to access the published file via the <b><a href='%s'>Loader</a></b> so
        long as they have access to the file's location on disk.

        <h3>Overwriting an existing publish</h3>
        Since all publishes are made immediately available to all consumers, a
        publish <b>cannot</b> be overwritten once it has been created. This is
        to ensure consistency and reproducibility for any consumers of the
        publish, such as downstream users or processes.
        """ % (loader_url,)

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
        schema = super(PublishFilesPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"] = ["file.*"]
        schema["Item Type Settings"]["default_value"] = DEFAULT_ITEM_TYPE_SETTINGS
        schema["Item Type Settings"]["values"]["items"] = {
            "publish_type": {
                "type": "shotgun_publish_type",
                "description": "",
            },
            "publish_name_template": {
                "type": "template",
                "description": "",
                "fields": ["context", "version", "[output]", "[name]", "*"],
                "allows_empty": True,
            },
            "publish_path_template": {
                "type": "template",
                "description": "",
                "fields": ["context", "*"],
                "allows_empty": True,
            },
            "publish_symlink_template": {
                "type": "template",
                "description": "",
                "fields": ["context", "*"],
                "allows_empty": True,
            },
            "publish_linked_entity_name_template": {
                "type": "template",
                "description": "",
                "fields": ["context", "version", "[output]", "[name]", "*"],
                "allows_empty": True,
            },
            "additional_publish_fields": {
                "type": "dict",
                "values": {
                    "type": "str",
                },
                "default_value": {"name": "sg_element", "output": "sg_output"},
                "description": (
                    "Dictionary of template_key/sg_field pairs to populate on "
                    "the PublishedFile entity."
                )
            }
        }
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
        accept_data = super(PublishFilesPlugin, self).accept(task_settings, item)
        if not accept_data.get("accepted"):
            return accept_data

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
            return accept_data

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

        publisher = self.parent

        # ---- ensure that work file(s) exist on disk to be published

        if item.properties.is_sequence:
            if not item.properties.sequence_paths:
                self.logger.warning("File sequence does not exist: %s" % item.properties.path)
                return False
        else:
            if not os.path.exists(item.properties.path):
                self.logger.warning("File does not exist: %s" % item.properties.path)
                return False

        # ---- validate the settings required to publish

        attr_list = ("publish_type", "publish_path", "publish_name", "publish_version",
                     "publish_symlink_path", "publish_linked_entity_name")
        for attr in attr_list:
            try:
                method = getattr(self, "_get_%s" % attr)
                item.properties[attr] = method(item, task_settings)
            except Exception:
                self.logger.error(
                    "Unable to determine '%s' for item: %s" % (attr, item.name),
                    extra={
                        "action_show_more_info": {
                            "label": "Show Error Log",
                            "tooltip": "Show the error log",
                            "text": traceback.format_exc()
                        }
                    }
                )
                return False

        # ---- check for conflicting publishes of this path with a status

        # Note the name, context, and path *must* match the values supplied to
        # register_publish in the publish phase in order for this to return an
        # accurate list of previous publishes of this file.
        publishes = publisher.util.get_conflicting_publishes(
            item.context,
            item.properties.publish_path,
            item.properties.publish_name,
            filters=["sg_status_list", "is_not", None]
        )

        if publishes:
            conflict_info = (
                "If you continue, these conflicting publishes will no longer "
                "be available to other users via the loader:<br>"
                "<pre>%s</pre>" % (pprint.pformat(publishes),)
            )
            self.logger.warning(
                "Found %s conflicting publishes in Shotgun" %
                    (len(publishes),),
                extra={
                    "action_show_more_info": {
                        "label": "Show Conflicts",
                        "tooltip": "Show the conflicting publishes in Shotgun",
                        "text": conflict_info
                    }
                }
            )

        # this means it's an in-place publish
        if item.properties.publish_path != item.properties.path:

            # ---- ensure the published file(s) don't already exist on disk
            conflict_info = None
            if item.properties.is_sequence:
                seq_pattern = publisher.util.get_path_for_frame(item.properties.publish_path, "*")
                seq_files = [f for f in glob.iglob(seq_pattern) if os.path.isfile(f)]

                if seq_files:
                    conflict_info = (
                        "The following files already exist!<br>"
                        "<pre>%s</pre>" % (pprint.pformat(seq_files),)
                    )
            else:
                if os.path.exists(item.properties.publish_path):
                    conflict_info = (
                        "The following file already exists!<br>"
                        "<pre>%s</pre>" % (item.properties.publish_path,)
                    )

            if conflict_info:
                self.logger.error(
                    "Version '%s' of this file already exists on disk." %
                        (item.properties.publish_version,),
                    extra={
                        "action_show_more_info": {
                            "label": "Show Conflicts",
                            "tooltip": "Show the conflicting published files",
                            "text": conflict_info
                        }
                    }
                )
                return False

        self.logger.info(
            "A Publish will be created for item '%s'." %
                (item.name,),
            extra={
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": "Publish Name: %s" % (item.properties.publish_name,) + "\n" +
                            "Linked Entity Name: %s" % (item.properties.publish_linked_entity_name,) + "\n" +
                            "Publish Path: %s" % (item.properties.publish_path,) + "\n" +
                            "Publish Symlink Path: %s" % (item.properties.publish_symlink_path,)
                }
            }
        )

        return True


    def publish(self, task_settings, item):
        """
        Executes the publish logic for the given item and task_settings.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent

        # Get item properties populated by validate method
        publish_name          = item.properties.publish_name
        publish_path          = item.properties.publish_path
        publish_symlink_path  = item.properties.publish_symlink_path
        publish_type          = item.properties.publish_type
        publish_version       = item.properties.publish_version

        # handle copying of work to publish
        # do not copy in case of in-place publish!
        if publish_path != item.properties.path:
            self._copy_files(publish_path, item)

        # symlink the files if it's defined in publish templates
        if publish_symlink_path:
            self._symlink_files(item)

        # Get any upstream dependency paths
        dependency_paths = item.properties.get("publish_dependencies", [])

        # If the parent item has publish data, include those ids in the
        # list of dependencies as well
        dependency_ids = []
        if "sg_publish_data_list" in item.parent.properties:
            [dependency_ids.append(sg_publish_data["id"]) for sg_publish_data in item.parent.properties["sg_publish_data_list"]]

        # get any additional_publish_fields that have been defined
        sg_fields = {}
        additional_fields = task_settings.get("additional_publish_fields").value or {}
        for template_key, sg_field in additional_fields.iteritems():
            if template_key in item.properties.fields:
                sg_fields[sg_field] = item.properties.fields[template_key]

        # 769: update sg_path_to_source field
        sg_fields["sg_path_to_source"] = item.properties.path

        # arguments for publish registration
        self.logger.info("Registering publish...")
        publish_data = {
            "tk": publisher.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": publish_path,
            "name": publish_name,
            "version_number": publish_version,
            "thumbnail_path": item.get_thumbnail_as_path() or "",
            "published_file_type": publish_type,
            "dependency_ids": dependency_ids,
            "dependency_paths": dependency_paths,
            "sg_fields": sg_fields
        }

        # log the publish data for debugging
        self.logger.debug(
            "Populated Publish data...",
            extra={
                "action_show_more_info": {
                    "label": "Publish Data",
                    "tooltip": "Show the complete Publish data dictionary",
                    "text": "<pre>%s</pre>" % (pprint.pformat(publish_data),)
                }
            }
        )

        exception = None
        sg_publish_data = None
        # create the publish and stash it in the item properties for other
        # plugins to use.
        try:
            sg_publish_data = sgtk.util.register_publish(**publish_data)
            self.logger.info("Publish registered!")
        except Exception as e:
            exception = e
            self.logger.error(
                "Couldn't register Publish for %s" % item.name,
                extra={
                    "action_show_more_info": {
                        "label": "Show Error Log",
                        "tooltip": "Show the error log",
                        "text": traceback.format_exc()
                    }
                }
            )

        if not sg_publish_data:
            self.undo(task_settings, item)
        else:
            if "sg_publish_data_list" not in item.properties:
                item.properties.sg_publish_data_list = []

            # add the publish data to item properties
            item.properties.sg_publish_data_list.append(sg_publish_data)

        if exception:
            raise exception

    def undo(self, task_settings, item):
        """
        Execute the undo method. This method will
        delete the files that have been copied to the disk
        it will also delete any PublishedFile entity that got created due to the publish.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        self.logger.info("Cleaning up copied files for %s..." % item.name)

        sg_publish_data_list = item.properties.get("sg_publish_data_list")
        publish_path = item.properties.get("publish_path")
        publish_symlink_path = item.properties.get("publish_symlink_path")

        if publish_symlink_path:
            self._delete_files(publish_symlink_path, item)

        if publish_path:
            self._delete_files(publish_path, item)

        if sg_publish_data_list:
            for publish_data in sg_publish_data_list:
                try:
                    self.sgtk.shotgun.delete(publish_data["type"], publish_data["id"])
                    self.logger.info("Cleaning up published file...",
                                     extra={
                                         "action_show_more_info": {
                                             "label": "Publish Data",
                                             "tooltip": "Show the publish data.",
                                             "text": "%s" % publish_data
                                         }
                                     }
                                     )
                except Exception:
                    self.logger.error(
                        "Failed to delete PublishedFile Entity for %s" % item.name,
                        extra={
                            "action_show_more_info": {
                                "label": "Show Error Log",
                                "tooltip": "Show the error log",
                                "text": traceback.format_exc()
                            }
                        }
                    )
            # pop the sg_publish_data_list too
            item.properties.pop("sg_publish_data_list")


    def finalize(self, task_settings, item):
        """
        Execute the finalization pass. This pass executes once
        all the publish tasks have completed, and can for example
        be used to version up files.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        if "sg_publish_data_list" in item.properties:
            publisher = self.parent

            # get the data for the publish that was just created in SG
            sg_publish_data_list = item.properties.sg_publish_data_list

            for publish_data in sg_publish_data_list:
                # ensure conflicting publishes have their status cleared
                publisher.util.clear_status_for_conflicting_publishes(
                    item.context, publish_data)

                self.logger.info(
                    "Publish created for file: %s" % (publish_data["path"]["local_path"],),
                    extra={
                        "action_show_in_shotgun": {
                            "label": "Show Publish",
                            "tooltip": "Open the Publish in Shotgun.",
                            "entity": publish_data
                        }
                    }
                )

            self.logger.info("Cleared the status of all previous, conflicting publishes")


    ############################################################################
    # protected methods

    def _get_publish_type(self, item, task_settings):
        """
        Get a publish type for the supplied item.

        :param item: The item to determine the publish type for

        :return: A publish type or None if one could not be found.
        """
        publish_type = task_settings.get("publish_type").value
        if not publish_type:
            raise TankError("publish_type not set for item: %s" % item.name)

        return publish_type


    def _get_publish_path(self, item, task_settings):
        """
        Get a publish path for the supplied item.

        :param item: The item to determine the publish type for

        :return: A string representing the output path to supply when
            registering a publish for the supplied item

        Extracts the publish path via the configured publish templates
        if possible.
        """

        publisher = self.parent

        # Start with the item's fields
        fields = copy.copy(item.properties.get("fields", {}))

        publish_path_template = task_settings.get("publish_path_template").value
        publish_path = None

        # If a template is defined, get the publish path from it
        if publish_path_template:

            pub_tmpl = publisher.get_template_by_name(publish_path_template)
            if not pub_tmpl:
                # this template was not found in the template config!
                raise TankError("The Template '%s' does not exist!" % publish_path_template)

            # First get the fields from the context
            try:
                fields.update(item.context.as_template_fields(pub_tmpl))
            except TankError, e:
                self.logger.debug(
                    "Unable to get context fields for publish_path_template.")

            missing_keys = pub_tmpl.missing_keys(fields, True)
            if missing_keys:
                raise TankError(
                    "Cannot resolve publish_path_template (%s). Missing keys: %s" %
                            (publish_path_template, pprint.pformat(missing_keys))
                )

            # Apply fields to publish_path_template to get publish path
            publish_path = pub_tmpl.apply_fields(fields)
            self.logger.debug(
                "Used publish_path_template to determine the publish path: %s" %
                (publish_path,)
            )

        # Otherwise fallback to publishing in place
        else:
            publish_path = item.properties.path
            self.logger.debug(
                "No publish_path_template defined. Publishing in place.")

        return publish_path

    def _get_publish_symlink_path(self, item, task_settings):
        """
        Get a publish symlink path for the supplied item.

        :param item: The item to determine the publish type for

        :return: A string representing the symlink path to supply when
            registering a publish for the supplied item

        Extracts the publish symlink path via the configured publish templates
        if possible.
        """

        publisher = self.parent

        # Start with the item's fields
        fields = copy.copy(item.properties.get("fields", {}))

        publish_symlink_template = task_settings.get("publish_symlink_template").value
        publish_symlink_path = None

        # If a template is defined, get the publish symlink path from it
        if publish_symlink_template:

            pub_symlink_tmpl = publisher.get_template_by_name(publish_symlink_template)
            if not pub_symlink_tmpl:
                # this template was not found in the template config!
                raise TankError("The Template '%s' does not exist!" % publish_symlink_template)

            # First get the fields from the context
            try:
                fields.update(item.context.as_template_fields(pub_symlink_tmpl))
            except TankError, e:
                self.logger.debug(
                    "Unable to get context fields for publish_symlink_template.")

            missing_keys = pub_symlink_tmpl.missing_keys(fields, True)
            if missing_keys:
                raise TankError(
                    "Cannot resolve publish_symlink_template (%s). Missing keys: %s" %
                            (publish_symlink_template, pprint.pformat(missing_keys))
                )

            # Apply fields to publish_symlink_template to get publish symlink path
            publish_symlink_path = pub_symlink_tmpl.apply_fields(fields)
            self.logger.debug(
                "Used publish_symlink_template to determine the publish path: %s" %
                (publish_symlink_path,)
            )

        return publish_symlink_path


    def _get_publish_version(self, item, task_settings):
        """
        Get the publish version for the supplied item.

        :param item: The item to determine the publish version for

        Extracts the publish version from the item's "version" field
        """

        # Get the publish version from the item's fields
        return item.properties.fields.get("version", 1)


    def _get_publish_name(self, item, task_settings):
        """
        Get the publish name for the supplied item.

        :param item: The item to determine the publish version for

        Uses the path info hook to retrieve the publish name.
        """

        publisher = self.parent

        # Start with the item's fields
        fields = copy.copy(item.properties.get("fields", {}))

        publish_name_template = task_settings.get("publish_name_template").value
        publish_name = None

        # First check if we have a publish_name_template defined and attempt to
        # get the publish name from that
        if publish_name_template:

            pub_tmpl = publisher.get_template_by_name(publish_name_template)
            if not pub_tmpl:
                # this template was not found in the template config!
                raise TankError("The Template '%s' does not exist!" % publish_name_template)

            # First get the fields from the context
            try:
                fields.update(item.context.as_template_fields(pub_tmpl))
            except TankError, e:
                self.logger.debug(
                    "Unable to get context fields for publish_name_template.")

            missing_keys = pub_tmpl.missing_keys(fields, True)
            if missing_keys:
                raise TankError(
                    "Cannot resolve publish_name_template (%s). Missing keys: %s" %
                            (publish_name_template, pprint.pformat(missing_keys))
                )

            publish_name = pub_tmpl.apply_fields(fields)
            self.logger.debug(
                "Retrieved publish_name via publish_name_template.")

        # Otherwise fallback on file path parsing
        else:
            # Use built-in method for determining publish_name
            publish_name = publisher.util.get_publish_name(item.properties.path)
            self.logger.debug(
                "Retrieved publish_name via source file path.")

        return publish_name

    def _get_publish_linked_entity_name(self, item, task_settings):
        """
        Get the linked entity name for the supplied item.

        :param item: The item to determine the publish version for
        """

        publisher = self.parent

        # Start with the item's fields
        fields = copy.copy(item.properties.get("fields", {}))

        publish_linked_entity_name_template = task_settings.get("publish_linked_entity_name_template").value
        publish_linked_entity_name = None

        # check if we have a publish_linked_entity_name_template defined
        if publish_linked_entity_name_template:

            pub_linked_entity_name_tmpl = publisher.get_template_by_name(publish_linked_entity_name_template)
            if not pub_linked_entity_name_tmpl:
                # this template was not found in the template config!
                raise TankError("The Template '%s' does not exist!" % publish_linked_entity_name_template)

            # First get the fields from the context
            try:
                fields.update(item.context.as_template_fields(pub_linked_entity_name_tmpl))
            except TankError, e:
                self.logger.debug(
                    "Unable to get context fields for publish_linked_entity_name_template.")

            missing_keys = pub_linked_entity_name_tmpl.missing_keys(fields, True)
            if missing_keys:
                raise TankError(
                    "Cannot resolve publish_linked_entity_name_template (%s). Missing keys: %s" %
                            (publish_linked_entity_name_template, pprint.pformat(missing_keys))
                )

            publish_linked_entity_name = pub_linked_entity_name_tmpl.apply_fields(fields)
            self.logger.debug(
                "Retrieved publish_linked_entity_name via publish_linked_entity_name_template.")

        return publish_linked_entity_name
