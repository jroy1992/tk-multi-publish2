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
import sys
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class UploadVersionPlugin(HookBaseClass):
    """
    Plugin for sending quicktimes and images to shotgun for review.
    """

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """
        # look for icon one level up from this hook's folder in "icons" folder
        return self.parent.expand_path("{self}/hooks/icons/review.png")

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Upload for Review"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        publisher = self.parent

        shotgun_url = publisher.sgtk.shotgun_url

        media_page_url = "%s/page/media_center" % (shotgun_url,)
        review_url = "https://www.shotgunsoftware.com/features/#review"

        return """
        Upload the file to Shotgun for review.<br><br>

        A <b>Version</b> entry will be created in Shotgun and a transcoded
        copy of the file will be attached to it. The file can then be reviewed
        via the project's <a href='%s'>Media</a> page, <a href='%s'>RV</a>, or
        the <a href='%s'>Shotgun Review</a> mobile app.
        """ % (media_page_url, review_url, review_url)

        # TODO: when settings editable, describe upload vs. link

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
        schema = super(UploadVersionPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"] = ["file.texture", "file.image", "file.video"]

        schema["Upload"] = {
            "type": "bool",
            "default_value": True,
            "description": "Upload content to Shotgun"
        }
        schema["Link Local File"] = {
            "type": "bool",
            "default_value": True,
            "description": "Should the local file be referenced by Shotgun"
        }
        return schema


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

        path = item.properties.get("path")
        if not path:
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
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: True if item is valid, False otherwise.
        """
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
        path = item.properties.path

        # allow the publish name to be supplied via the task_settings. this is
        # useful for collectors that have access to templates and can determine
        # publish information about the item that doesn't require further, fuzzy
        # logic to be used here (the zero config way)
        publish_name = item.properties.get("publish_name")
        if not publish_name:

            self.logger.debug("Using path info hook to determine publish name.")

            # use the path's filename as the publish name
            path_components = publisher.util.get_file_path_components(path)
            publish_name = path_components["filename"]

        self.logger.debug("Publish name: %s" % (publish_name,))

        self.logger.info("Creating Version...")
        version_data = {
            "project": item.context.project,
            "code": publish_name,
            "description": item.description,
            "entity": self._get_version_entity(item),
            "sg_task": item.context.task
        }

        if "sg_publish_data_list" in item.properties:
            version_data["published_files"] = item.properties.sg_publish_data_list

        if task_settings["Link Local File"].value:
            version_data["sg_path_to_movie"] = path

        # log the version data for debugging
        self.logger.debug(
            "Populated Version data...",
            extra={
                "action_show_more_info": {
                    "label": "Version Data",
                    "tooltip": "Show the complete Version data dictionary",
                    "text": "<pre>%s</pre>" % (pprint.pformat(version_data),)
                }
            }
        )

        # Create the version
        version = publisher.shotgun.create("Version", version_data)
        self.logger.info("Version created!")

        # stash the version info in the item just in case
        item.properties.sg_version_data = version

        thumb = item.get_thumbnail_as_path()

        if task_settings["Upload"].value:
            self.logger.info("Uploading content...")

            # on windows, ensure the path is utf-8 encoded to avoid issues with
            # the shotgun api
            if sys.platform.startswith("win"):
                upload_path = path.decode("utf-8")
            else:
                upload_path = path

            self.parent.shotgun.upload(
                "Version",
                version["id"],
                upload_path,
                "sg_uploaded_movie"
            )
        elif thumb:
            # only upload thumb if we are not uploading the content. with
            # uploaded content, the thumb is automatically extracted.
            self.logger.info("Uploading thumbnail...")
            self.parent.shotgun.upload_thumbnail(
                "Version",
                version["id"],
                thumb
            )

        self.logger.info("Upload complete!")


    def finalize(self, task_settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        path = item.properties.path
        version = item.properties.sg_version_data

        self.logger.info(
            "Version uploaded for file: %s" % (path,),
            extra={
                "action_show_in_shotgun": {
                    "label": "Show Version",
                    "tooltip": "Reveal the version in Shotgun.",
                    "entity": version
                }
            }
        )


    def _get_version_entity(self, item):
        """
        Returns the best entity to link the version to.
        """

        if item.context.entity:
            return item.context.entity
        elif item.context.project:
            return item.context.project
        else:
            return None
