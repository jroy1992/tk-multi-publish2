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
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


SESSION_ITEM_TYPE_FILTERS = []
SESSION_ITEM_TYPE_SETTINGS = {}

class SessionPublishPlugin(HookBaseClass):
    """
    Inherits from PublishPlugin
    """
    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish Session"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        desc = super(SessionPublishPlugin, self).description

        return desc + "<br><br>" + """
        After publishing, if a version number is detected in the file, the file
        will automatically be saved to the next incremental version number.
        For example, <code>filename.v001.ext</code> will be published and copied
        to <code>filename.v002.ext</code>

        If the next incremental version of the file already exists on disk, the
        validation step will produce a warning, and a button will be provided in
        the logging output which will allow saving the session to the next
        available version number prior to publishing.

        <br><br><i>NOTE: any amount of version number padding is supported.</i>
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
        schema = super(SessionPublishPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"] = SESSION_ITEM_TYPE_FILTERS
        schema["Item Type Settings"]["default_value"] = SESSION_ITEM_TYPE_SETTINGS
        return schema


    def publish(self, task_settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        # ensure the session is saved
        self.logger.info("Saving the current session...")
        self._save_session(item.properties.get("path"), item)

        # Store any file/id dependencies
        item.properties.publish_dependency_paths = self._get_dependency_paths()
        item.properties.publish_dependency_ids = self._get_dependency_ids()

        super(SessionPublishPlugin, self).publish(task_settings, item)


    def finalize(self, task_settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        publisher = self.parent

        super(SessionPublishPlugin, self).finalize(task_settings, item)

        # version up the scene file if the publish went through successfully.
        path = item.properties.get("path"):
        if path and item.properties.get("sg_publish_data_list"):

            # insert the next version path into the properties
            item.properties.next_version_path = publisher.util.save_to_next_version(
                path,
                self._save_session,
                item
            )


    def _get_dependency_paths(self, node=None):
        """
        Find all dependency paths for the current node. If no node specified,
        will return all dependency paths for the session.

        :param node: Optional node to process
        :return: List of upstream dependency paths
        """
        raise NotImplementedError


    def _get_dependency_ids(self, node=None):
        """
        Find all dependency ids for the current node. If no node specified,
        will return all dependency ids for the session.

        :param node: Optional node to process
        :return: List of upstream dependency ids
        """
        raise NotImplementedError


    def _save_session(self, path, item):
        """
        Save the current session to the supplied path.
        """
        raise NotImplementedError
