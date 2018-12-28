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


class PublishPlugin(HookBaseClass):
    """
    Plugin for creating generic publishes in Shotgun.

    This plugin is configured as a base class for other publish plugins as it
    contains standard operations for validating and registering publishes with Shotgun.

    Once attached to a publish item, the plugin will key off of properties that
    drive how the item is published.

    The following properties can be set on the item via the collector or by
    subclasses prior to calling methods on the base class::

        ``path`` - A path to the source file of the item.

        ``sequence_paths`` - If set, implies the "path" property represents a
            sequence of files (typically using a frame identifier such as %04d).
            This property should be a list of files on disk matching the "path".

        ``is_sequence`` - A boolean defining whether or not this item is a sequence of files.

        ``publish_dependency_ids`` - A list of entity dictionaries containing (at least)
            id and type keys to include as dependencies when registering the publish.

        ``publish_dependency_paths`` - A list of files to include as dependencies when
            registering the publish. If the item's parent has been published,
            it's path will be appended to this list.

        ``publish_user`` - If set, will be supplied to SG as the publish user
            when registering the new publish. If not available, the publishing
            will fall back to the :meth:`tank.util.register_publish` logic.


    The following are the item_type-specific settings that are available for each task instance::

        publish_type - If set in the plugin settings dictionary, will be
            supplied to SG as the publish type when registering "path" as a new
            publish. This is required.

        publish_name_template - If set in the plugin settings dictionary, will be
            supplied to SG as the publish name when registering the new publish.
            If not available, will fall back to the ``path_info`` hook logic.

        publish_path_template - If set in the plugin settings dictionary, used to
            determine where "path" should be copied prior to publishing. If
            not specified, "path" will be published in place.

    The following properties are set during the execution of this plugin, and can be
    accessed via :meth:`Item.properties` or :meth:`Item.local_properties`.

        publish_type - Shotgun PublishedFile instance type.

        publish_name - Shotgun PublishedFile instance name.

        publish_version - Shotgun PublishedFile instance version.

        publish_path - The location on disk the publish is copied to.

        sg_publish_data_list - The list of entity dictionaries corresponding to the
            publish information returned from the tk-core register_publish method.

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
        return "Publish to Shotgun"

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
        schema = super(PublishPlugin, self).settings_schema
        schema["Item Type Settings"]["values"]["items"] = {
            "publish_type": {
                "type": "shotgun_publish_type",
                "description": "",
            },
            "publish_name_template": {
                "type": "template",
                "description": "",
                "fields": "context, version, [output], [name], *",
                "allows_empty": True,
            },
            "publish_path_template": {
                "type": "template",
                "description": "",
                "fields": "context, *",
                "allows_empty": True,
            },
            "publish_symlink_template": {
                "type": "template",
                "description": "",
                "fields": "context, *",
                "allows_empty": True,
            },
            "publish_linked_entity_name_template": {
                "type": "template",
                "description": "",
                "fields": "context, version, [output], [name], *",
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


    def init_task_settings(self, item):
        """
        Method called by the publisher to determine the initial settings for the
        instantiated task.

        :param item: The parent item of the task
        :returns: dictionary of settings for this item's task
        """
        # Return the item-type specific settings
        if item.type not in self.plugin.settings["Item Type Settings"]:
            msg = "Key: %s\n%s" % (item.type, pprint.pformat(self.plugin.settings["Item Type Settings"]))
            self.logger.warning(
                "'Item Type Settings' are missing for item type: '%s'" % item.type,
                extra={
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show more info",
                        "text": msg
                    }
                }
            )
            return {}
        return self.plugin.settings["Item Type Settings"].get(item.type)


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

        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """
        accept_data = {}

        # Only accept this item if we have its task settings dict
        if not task_settings:
            msg = "Unable to find task_settings for plugin: %s" % self.name
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
        accept_data["accepted"] = True
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

        # ---- validate the settings required to publish

        attr_list = ("publish_type", "publish_name", "publish_version", "publish_path",
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
                "Found %s conflicting publishes in Shotgun" % (len(publishes),),
                extra={
                    "action_show_more_info": {
                        "label": "Show Conflicts",
                        "tooltip": "Show the conflicting publishes in Shotgun",
                        "text": conflict_info
                    }
                }
            )

        if item.properties.get("is_sequence"):
            path = publisher.util.get_path_for_frame(item.properties.path, "*")
            publish_path = publisher.util.get_path_for_frame(item.properties.publish_path, "*")
        else:
            path = item.properties.get("path")
            publish_path = item.properties.publish_path

        # ---- check if its an in place publish
        if path != publish_path:
            # ---- ensure the published file(s) don't already exist on disk

            conflict_info = None
            if item.properties.get("is_sequence"):
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
        publish_user          = item.get_property("publish_user", default_value=None)

        # handle publishing of files first
        self.publish_files(task_settings, item, publish_path)

        # symlink the files if it's defined in publish templates
        if publish_symlink_path:
            self.symlink_publishes(task_settings, item)

        # Get any upstream dependency paths
        dependency_paths = item.properties.get("publish_dependency_paths", [])

        # Get any upstream dependency ids
        dependency_ids = item.properties.get("publish_dependency_ids", [])

        # If the parent item has publish data, include those ids in the
        # list of dependencies as well
        if "sg_publish_data_list" in item.parent.properties:
            dependency_ids.extend([ent["id"] for ent in item.parent.properties["sg_publish_data_list"]])

        # get any additional_publish_fields that have been defined
        sg_fields = {}
        additional_fields = task_settings.get("additional_publish_fields").value or {}
        for template_key, sg_field in additional_fields.iteritems():
            if template_key in item.properties.fields:
                sg_fields[sg_field] = item.properties.fields[template_key]

        # If we have a source file path, add it to the publish metadata
        path = item.properties.get("path")
        if path:
            sg_fields["sg_path_to_source"] = path

        # Make sure any specified fields exist on the PublishedFile entity
        sg_fields = self._validate_sg_fields(sg_fields)

        # arguments for publish registration
        self.logger.info("Registering publish...")
        publish_data = {
            "tk": publisher.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": publish_path,
            "name": publish_name,
            "created_by": publish_user,
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
            self.logger.debug(
                "Shotgun Publish data...",
                extra={
                    "action_show_more_info": {
                        "label": "Shotgun Publish Data",
                        "tooltip": "Show the complete Shotgun Publish Entity dictionary",
                        "text": "<pre>%s</pre>" % (pprint.pformat(sg_publish_data),)
                    }
                }
            )
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
            self.delete_files(task_settings, item, publish_symlink_path)

        # Delete any files on disk
        self.delete_files(task_settings, item, publish_path)

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


    def publish_files(self, task_settings, item, publish_path):
        """
        This method publishes (copies) the item's path property to the publish location.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :param publish_path: The output path to publish files to
        """
        publisher = self.parent

        path = item.properties.get("path")
        if not path:
            raise KeyError("Base class implementation of publish_files() method requires a 'path' property.")

        # ---- get a list of files to be copied
        is_sequence = item.properties.get("is_sequence", False)
        if is_sequence:
            work_files = item.properties.get("sequence_paths", [])
        else:
            work_files = [path]

        # Determine if we should seal the copied files or not
        seal_files = item.properties.get("seal_files", False)

        return publisher.util.copy_files(work_files, publish_path, seal_files=seal_files, is_sequence=is_sequence)


    def symlink_publishes(self, task_settings, item):
        """
        This method handles symlinking an item's publish_path to publish_symlink_path,
        assuming publish_symlink_path is already populated.
        """
        publisher = self.parent

        publish_path = item.properties.publish_path
        symlink_path = item.properties.publish_symlink_path

        # ---- get a list of files to be symlinked
        seq_path = publisher.util.get_frame_sequence_path(publish_path)
        if seq_path:
            src_files = publisher.util.get_sequence_path_files(publish_path)
            is_sequence = True
        else:
            src_files = [publish_path]
            is_sequence = False

        return publisher.util.symlink_files(src_files, symlink_path, is_sequence)


    def delete_files(self, task_settings, item, deletion_path):
        """
        This method handles deleting an item's path(s) from a designated location.
        """
        publisher = self.parent

        # ---- get a list of files to be deleted
        seq_path = publisher.util.get_frame_sequence_path(deletion_path)
        if seq_path:
            files_to_delete = publisher.util.get_sequence_path_files(seq_path)
        else:
            files_to_delete = [deletion_path]

        return publisher.util.delete_files(files_to_delete)


    ############################################################################
    # protected methods

    def _validate_sg_fields(self, sg_fields):
        """
        Ensure that the requested sg_fields exist in the PublishedFile entity schema

        :param sg_fields: A dictionary of field:value pairs to set on the PublishedFile entity

        :return: A dictionary of valid field:value pairs that match the PublishedFile schema
        """
        publish_entity_type = sgtk.util.get_published_file_entity_type(self.parent.sgtk)
        try:
            fields = self.parent.shotgun.schema_field_read(publish_entity_type)
        except Exception, e:
            self.logger.error("Failed to find fields for the '%s' schema: %s"
                              % (publish_entity_type, e))

        bad_fields = list(set(sg_fields.keys()).difference(set(fields)))
        if bad_fields:
            self.logger.warning(
                    "The '%s' schema does not support these fields: %s. Skipping." % \
                    (publish_entity_type, pprint.pformat(bad_fields))
            )

        # Return the subset of valid fields
        return {k: v for k, v in sg_fields.iteritems() if k not in bad_fields}


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

        # Update the version field with the publish_version
        fields["version"] = item.properties.publish_version

        publish_path_template = task_settings.get("publish_path_template").value
        publish_path = item.properties.get("path")

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

        # Otherwise, if the item has an input path, fallback to publishing in place
        elif publish_path:
            self.logger.debug(
                "No publish_path_template defined. Publishing in place.")

        # return the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        return sgtk.util.ShotgunPath.normalize(publish_path)


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

        # Update the version field with the publish_version
        fields["version"] = item.properties.publish_version

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
        # Return none if this is the root item
        if item.is_root:
            return None

        # First see if we can get the publish version from the parent
        parent_version = self._get_publish_version(item.parent, task_settings)
        if parent_version:
            # Note - this intentionally stomps on any local evaluation as all children
            # should match their parent's publish version number
            return parent_version

        publish_name = item.properties.publish_name
        publish_type = item.properties.publish_type

        # First find existing publishes to determine if this version has already been published
        existing_publishes = self._find_publishes(self.parent.context, publish_name, publish_type)
        publish_versions = [p["version_number"] for p in existing_publishes]

        # The get the version number from the path, if defined
        version = int(item.properties.fields.get("version", 1))

        # Find the first value equal to or greater than the file version that doesn't already exist
        while True:
            try:
                publish_versions.index(version)
            except ValueError:
                break
            else:
                version += 1

        return version


    def _find_publishes(self, ctx, publish_name, publish_type):
        """
        Given a context, publish name and type, find all publishes from Shotgun
        that match.

        :param ctx:             Context to use when looking for publishes
        :param publish_name:    The name of the publishes to look for
        :param publish_type:    The type of publishes to look for

        :returns:               A list of Shotgun publish records that match the search
                                criteria
        """
        publisher = self.parent

        publish_entity_type = sgtk.util.get_published_file_entity_type(self.parent.sgtk)
        if publish_entity_type == "PublishedFile":
            publish_type_field = "published_file_type.PublishedFileType.code"
        else:
            publish_type_field = "tank_type.TankType.code"

        # construct filters from the context:
        filters = [["project", "is", ctx.project]]
        if ctx.entity:
            filters.append(["entity", "is", ctx.entity])
        if ctx.task:
            filters.append(["task", "is", ctx.task])

        # add in name & type:
        if publish_name:
            filters.append(["name", "starts_with", publish_name])
        if publish_type:
            filters.append([publish_type_field, "is", publish_type])

        # retrieve a list of all matching publishes from Shotgun:
        sg_publishes = []
        try:
            query_fields = ["version_number"]
            sg_publishes = self.parent.shotgun.find(publish_entity_type, filters, query_fields)
        except Exception, e:
            self.logger.error("Failed to find publishes of type '%s', called '%s', for context %s: %s"
                              % (publish_type, publish_name, ctx, e))
        return sg_publishes


    def _get_publish_name(self, item, task_settings):
        """
        Get the publish name for the supplied item.

        :param item: The item to determine the publish version for

        Uses the path info hook to retrieve the publish name.
        """

        publisher = self.parent

        # Get the input path for this item
        path = item.properties.get("path")

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

        # Otherwise, if the item has an input path, fallback on file path parsing
        elif path:
            # Use built-in method for determining publish_name
            publish_name = publisher.util.get_publish_name(path)
            self.logger.debug(
                "Retrieved publish_name via source file path.")

        self.logger.info("Found publish name: %s" % publish_name)
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
