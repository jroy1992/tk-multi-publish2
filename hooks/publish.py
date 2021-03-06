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
from sgtk import TankError, TankMissingTemplateError, TankMissingTemplateKeysError
from sgtk.platform import create_setting

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
        publisher = self.parent

        setting_key = "Item Type Settings"

        task_settings = super(PublishPlugin, self).init_task_settings(item)

        # If there are item-type specific settings, return a new dictionary
        # with just the settings for the current item_type.
        if item.type in task_settings["Item Type Settings"]:

            settings_value = copy.deepcopy(task_settings.raw_value)
            settings_schema = copy.deepcopy(task_settings.schema)

            # Get the item_type Setting obj
            item_type_setting = task_settings[setting_key].get(item.type)

            # Flatten the setting dictionary with the item_type's settings
            settings_value.update(item_type_setting.raw_value)
            if "items" not in settings_schema:
                settings_schema["items"] = {}
            settings_schema["items"].update(item_type_setting.schema.get("items", {}))

            # Create the new task_settings Setting object
            task_settings = create_setting(
                task_settings.name,
                settings_value,
                settings_schema,
                task_settings.bundle
            )
        # Else, warn the user...
        else:
            msg = "Key: %s\n%s" % (item.type, pprint.pformat(task_settings[setting_key]))
            self.logger.warning(
                "'%s' are missing for item type: '%s'" % (setting_key, item.type),
                extra={
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show more info",
                        "text": msg
                    }
                }
            )

        # Get the publish_version
        publish_version = self._get_publish_version(task_settings, item)

        # Initialize the fields dictionary for any template settings
        for setting in task_settings.itervalues():
            if setting.type == "template":
                setting.extra.setdefault("fields", {})

                # Add in any relevant keys stored on the item
                for k, v in item.get_property("fields", {}).iteritems():
                    setting.extra["fields"][k] = \
                        self.TemplateSettingWidget.TemplateField(
                            k, v, "str", editable=True, is_missing=False)

                # Add in the version key if applicable
                setting.extra["fields"]["version"] = \
                    self.TemplateSettingWidget.TemplateField(
                        "version", publish_version, "str", editable=False, is_missing=False)

        return task_settings


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

        attr_list = ("publish_version", "publish_linked_entity_name", "publish_type",
                     "publish_name", "publish_path", "publish_symlink_path")

        if not self._set_item_properties(task_settings, item, attr_list, set_local=True):
            return False

        # ---- check for conflicting publishes of this path with a status

        # Note the name, context, and path *must* match the values supplied to
        # register_publish in the publish phase in order for this to return an
        # accurate list of previous publishes of this file
        # and publishes with higher version number.
        # cache out the conflicting publishes in a property, so it can be used by other hooks.
        item.properties.conflicting_publishes = publisher.util.get_conflicting_publishes(
            item.context,
            item.get_property("publish_path"),
            item.get_property("publish_name"),
            filters=["sg_status_list", "is_not", None]
        )

        if item.properties.conflicting_publishes:
            conflict_info = (
                "Found the following conflicting publishes:<br>"
                "<pre>%s</pre>" % (pprint.pformat(item.properties.conflicting_publishes),)
            )
            self.logger.error(
                "Found %s conflicting publishes in Shotgun" % (len(item.properties.conflicting_publishes),),
                extra={
                    "action_show_more_info": {
                        "label": "Show Conflicts",
                        "tooltip": "Show the conflicting publishes in Shotgun",
                        "text": conflict_info
                    }
                }
            )
            return False

        if item.get_property("is_sequence") and item.get_property("path"):
            path = publisher.util.get_path_for_frame(item.get_property("path"), "*")
            publish_path = publisher.util.get_path_for_frame(item.get_property("publish_path"), "*")
        else:
            path = item.get_property("path")
            publish_path = item.get_property("publish_path")

        # ---- check if its an in place publish
        if path != publish_path:
            # ---- ensure the published file(s) don't already exist on disk

            conflict_info = None
            if item.get_property("is_sequence"):
                seq_pattern = publisher.util.get_path_for_frame(item.get_property("publish_path"), "*")
                seq_files = [f for f in glob.iglob(seq_pattern) if os.path.isfile(f)]

                if seq_files:
                    conflict_info = (
                        "The following published files already exist:<br>"
                        "<pre>%s</pre>" % (pprint.pformat(seq_files),)
                    )
            else:
                if os.path.exists(item.get_property("publish_path")):
                    conflict_info = (
                        "The following published file already exists!<br>"
                        "<pre>%s</pre>" % (item.get_property("publish_path"),)
                    )

            if conflict_info:
                self.logger.error(
                    "Found conflicting publishes for 'v%s' on disk." %
                    (item.get_property("publish_version"),),
                    extra={
                        "action_show_more_info": {
                            "label": "Show Conflicts",
                            "tooltip": "Show the conflicting published file(s)",
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
                    "text": "Publish Name: %s" % (item.get_property("publish_name"),) + "\n" +
                            "Linked Entity Name: %s" % (item.get_property("publish_linked_entity_name"),) + "\n" +
                            "Publish Path: %s" % (item.get_property("publish_path"),) + "\n" +
                            "Publish Symlink Path: %s" % (item.get_property("publish_symlink_path"),)
                }
            }
        )

        return True


    def _set_item_properties(self, task_settings, item, prop_list, set_local=False):
        """
        Given a list of properties, determine the value of each one by
        attempting to use a getter method and use this value to set the
        item's local or global properties.

        :param item:            Item whose properties are to be determined
        :param prop_list:       List of properties to be determined
        :param set_local:       Indicate whether local (plugin specific)
                                properties are to be set

        :return:                True if all properties are set, False if not
        """

        for property in prop_list:
            try:
                method = getattr(self, "_get_%s" % property)
                property_value = method(task_settings, item)
                if not item.properties.get(property):
                    # ensure global value for each property is set atleast once
                    item.properties[property] = property_value
                if set_local:
                    item.local_properties[property] = property_value
            except Exception:
                self.logger.error(
                    "Unable to determine '%s' for item: %s" % (property, item.name),
                    extra={
                        "action_show_more_info": {
                            "label": "Show Error Log",
                            "tooltip": "Show the error log",
                            "text": traceback.format_exc()
                        }
                    }
                )
                return False
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
        publish_name          = item.get_property("publish_name")
        publish_path          = item.get_property("publish_path")
        publish_symlink_path  = item.get_property("publish_symlink_path")
        publish_type          = item.get_property("publish_type")
        publish_version       = item.get_property("publish_version")
        publish_user          = item.get_property("publish_user", default_value=None)

        task_publish_paths = item.get_property("publish_paths_expanded", [])

        # handle publishing of files first
        task_publish_paths.append(self.publish_files(task_settings, item, publish_path))

        # symlink the files if it's defined in publish templates
        if publish_symlink_path:
            task_publish_paths.append(self.symlink_publishes(
                task_settings,
                item,
                publish_path,
                publish_symlink_path
            ))

        item.local_properties["publish_paths_expanded"] = task_publish_paths

        # Get any upstream dependency paths
        dependency_paths = self._get_dependency_paths(task_settings, item)

        # Get any upstream dependency ids
        dependency_ids = self._get_dependency_ids(task_settings, item)

        # If the parent item has publish data, include those ids in the
        # list of dependencies as well
        if item.parent.get_property("sg_publish_data_list"):
            dependency_ids.extend([ent["id"] for ent in item.parent.get_property("sg_publish_data_list")])

        # get any additional_publish_fields that have been defined
        sg_fields = {}
        additional_fields = task_settings.get("additional_publish_fields").value or {}
        for template_key, sg_field in additional_fields.iteritems():
            if template_key in item.get_property("fields"):
                sg_fields[sg_field] = item.get_property("fields")[template_key]

        # If we have a source file path, add it to the publish metadata
        path = item.get_property("path")
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
            item.properties.setdefault("sg_publish_data_list", [])
            item.local_properties.setdefault("sg_publish_data_list", [])

            # add the publish data to local and global item properties
            item.local_properties.sg_publish_data_list.append(sg_publish_data)
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

        task_publish_data_list = item.get_property("sg_publish_data_list")
        task_expanded_pub_paths = item.get_property("publish_paths_expanded")

        if task_expanded_pub_paths:
            # since we already have the actual paths, we don't need to re-expand
            # using delete_files()
            self.parent.util.delete_files(task_expanded_pub_paths)

        else:
            publish_path = item.get_property("publish_path")
            publish_symlink_path = item.get_property("publish_symlink_path")

            if publish_symlink_path:
                self.delete_files(task_settings, item, publish_symlink_path)

            # Delete any files on disk
            self.delete_files(task_settings, item, publish_path)

        if task_publish_data_list:
            for publish_data in task_publish_data_list:
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
            item.local_properties.pop("sg_publish_data_list")


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

        if item.get_property("sg_publish_data_list"):
            publisher = self.parent

            # get the data for the publish that was just created in SG
            task_publish_data_list = item.get_property("sg_publish_data_list")

            for publish_data in task_publish_data_list:
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

        path = item.get_property("path")
        if not path:
            raise KeyError("Base class implementation of publish_files() method requires a 'path' property.")

        # ---- get a list of files to be copied
        is_sequence = item.get_property("is_sequence", False)
        if is_sequence:
            work_files = item.get_property("sequence_paths", [])
        else:
            work_files = [path]

        # Determine if we should seal the copied files or not
        seal_files = item.get_property("seal_files", False)

        return publisher.util.copy_files(work_files, publish_path, seal_files=seal_files, is_sequence=is_sequence)


    def symlink_publishes(self, task_settings, item, publish_path, symlink_path):
        """
        This method handles symlinking an item's publish_path to publish_symlink_path.

        :param publish_path: The source path to link files from
        :param symlink_path: The dest path to create links at
        """
        publisher = self.parent

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
        except Exception as e:
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


    def _resolve_template_setting_value(self, setting, item):
        """Resolve the setting template value"""
        publisher = self.parent

        if not setting.value:
            return None

        # Start with the fields stored with the setting
        fields = {k: v.value for (k, v) in setting.extra["fields"].iteritems()}

        tmpl = publisher.get_template_by_name(setting.value)
        if not tmpl:
            # this template was not found in the template config!
            raise TankMissingTemplateError("The Template '%s' does not exist!" % setting.value)

        # First get the fields from the context
        try:
            fields.update(item.context.as_template_fields(tmpl))
        except TankError:
            self.logger.debug(
                "Unable to get context fields for publish_path_template.")

        missing_keys = tmpl.missing_keys(fields, True)
        if missing_keys:
            raise TankMissingTemplateKeysError(
                "Cannot resolve Template (%s). Missing keys: %s" %
                    (setting.value, pprint.pformat(missing_keys))
            )

        # Apply fields to template to get resolved value
        return tmpl.apply_fields(fields)


    def _get_publish_type(self, task_settings, item):
        """
        Get a publish type for the supplied item.

        :param item: The item to determine the publish type for

        :return: A publish type or None if one could not be found.
        """
        publish_type = task_settings.get("publish_type").value
        if not publish_type:
            raise TankError("publish_type not set for item: %s" % item.name)

        return publish_type


    def _get_publish_path(self, task_settings, item):
        """
        Get a publish path for the supplied item.

        :param item: The item to determine the publish path for

        :return: A string representing the output path to supply when
            registering a publish for the supplied item

        Extracts the publish path via the configured publish templates
        if possible.
        """
        publish_path_setting = task_settings.get("publish_path_template")
        publish_path = self._resolve_template_setting_value(publish_path_setting, item)
        if not publish_path:
            self.logger.debug("No publish_path_template defined. Publishing in place.")
            publish_path = item.properties.get("path")

        return sgtk.util.ShotgunPath.normalize(publish_path)


    def _get_publish_symlink_path(self, task_settings, item):
        """
        Get a publish symlink path for the supplied item.

        :param item: The item to determine the publish symlink path for

        :return: A string representing the symlink path to supply when
            registering a publish for the supplied item

        Extracts the publish symlink path via the configured publish templates
        if possible.
        """
        publish_path_setting = task_settings.get("publish_symlink_template")
        publish_path = self._resolve_template_setting_value(publish_path_setting, item)
        if publish_path:
            publish_path = sgtk.util.ShotgunPath.normalize(publish_path)

        return publish_path


    def _get_publish_version(self, task_settings, item):
        """
        Get the publish version for the supplied item.

        :param item: The item to determine the publish version for

        Extracts the publish version from the item's "version" field
        """
        # Return none if this is the root item
        if item.is_root:
            return None

        # First see if we can get the publish version from the parent
        parent_version = self._get_publish_version(task_settings, item.parent)
        if parent_version:
            # Note - this intentionally stomps on any local evaluation as all children
            # should match their parent's publish version number
            return parent_version

        # Get the publish version from the item's fields
        return item.properties.fields.get("version", 1)


    def _get_publish_name(self, task_settings, item):
        """
        Get the publish name for the supplied item.

        :param item: The item to determine the publish name for

        Uses the path info hook to retrieve the publish name.
        """
        publisher = self.parent

        publish_name_setting = task_settings.get("publish_name_template")
        publish_name = self._resolve_template_setting_value(publish_name_setting, item)
        if not publish_name:
            path = item.properties.get("path")
            # Use built-in method for determining publish_name
            publish_name = publisher.util.get_publish_name(path)
            self.logger.debug("Retrieved publish_name via source file path.")

        return publish_name


    def _get_publish_linked_entity_name(self, task_settings, item):
        """
        Get the linked entity name for the supplied item.

        :param item: The item to determine the publish linked entity name for
        """
        publish_name_setting = task_settings.get("publish_linked_entity_name_template")
        return self._resolve_template_setting_value(publish_name_setting, item)


    def _get_dependency_paths(self,  task_settings, item, node=None):
        """
        Find all dependency paths for the current item.

        :return: List of upstream dependency paths
        """
        return item.get_property("publish_dependency_paths", [])


    def _get_dependency_ids(self, task_settings, item, node=None):
        """
        Find all dependency ids for the current item.

        :return: List of upstream dependency ids
        """
        return item.get_property("publish_dependency_ids", [])
