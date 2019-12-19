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


class SessionPublishPlugin(HookBaseClass):
    """
    Inherits from PublishPlugin
    """

    SESSION_ITEM_TYPE_FILTERS = []
    SESSION_ITEM_TYPE_SETTINGS = {}

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
        schema["Item Type Filters"]["default_value"] = self.SESSION_ITEM_TYPE_FILTERS
        schema["Item Type Settings"]["default_value"] = self.SESSION_ITEM_TYPE_SETTINGS
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
        publisher = self.parent

        retval = super(SessionPublishPlugin, self).validate(task_settings, item)
        if not retval:
            return retval

        # Compare the work version to the publish version
        work_version = item.properties.fields.get("version", 1)
        publish_version = item.properties.publish_version

        # If the publish version is different (greater) than the current workfile version
        # then we should version up the workfile to match
        if work_version < publish_version:
            err_msg = "Publish version mismatch: Session v%s != Publish v%s." % \
                (work_version, publish_version)

            path = item.properties.get("path")
            if path:
                # Get the workfile path for the publish version...
                version = work_version
                while version < publish_version:
                    path = publisher.util.get_next_version_path(path)
                    if not path:
                        break
                    version = publisher.util.get_version_number(path)

                if os.path.exists(path):
                    self.logger.error(err_msg +
                        " Version v%s of this file already exists on disk." % version,
                        extra={
                            "action_show_folder": {
                                "path": path
                            }
                        }
                    )
                    return False

            self.logger.error(
                err_msg,
                extra={
                    "action_button": {
                        "label": "Save to v%s" % (publish_version,),
                        "tooltip": "Save session to match the publish version number: "
                                   "v%s" % (publish_version,),
                        "callback": lambda: self._save_session(path, publish_version, item)
                    }
                }
            )
            return False

        return True


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
        self._save_session(item.properties.get("path"), item.properties.publish_version, item)

        # Store any file/id dependencies
        item.local_properties["publish_dependency_paths"] = self._get_dependency_paths(task_settings, item)
        item.local_properties["publish_dependency_ids"] = self._get_dependency_ids(task_settings, item)

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
        path = item.properties.get("path")
        if path and item.properties.get("sg_publish_data_list"):

            # insert the next version path into the properties
            item.properties.next_version_path = publisher.util.save_to_next_version(
                path=path,
                save_callback=self._save_session,
                item=item
            )


    def _get_dependency_paths(self, task_settings, item, node=None):
        """
        Find all dependency paths for the current node. If no node specified,
        will return all dependency paths for the session.

        :param node: Optional node to process
        :return: List of upstream dependency paths
        """
        return []


    def _get_dependency_ids(self, task_settings, item, node=None):
        """
        Find all dependency ids for the current node. If no node specified,
        will return all dependency ids for the session.

        :param node: Optional node to process
        :return: List of upstream dependency ids
        """
        return []


    def _save_session(self, path, version, item):
        """
        Save the current session to the supplied path.
        """
        raise NotImplementedError
