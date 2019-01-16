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


class MariSessionPublishPlugin(HookBaseClass):
    """
    Inherits from SessionPublishPlugin
    """

    SESSION_ITEM_TYPE_FILTERS = ["mari.session"]
    SESSION_ITEM_TYPE_SETTINGS = {
        "mari.session": {
            "publish_type": "Mari Session",
            "publish_name_template": None,
            "publish_path_template": None
        }
    }

    def finalize(self, task_settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        super(MariSessionPublishPlugin, self).finalize(task_settings, item)

        # version up the session if the publish went through successfully.
        if item.properties.get("sg_publish_data_list"):
            # save the new version number in the session metadata
            next_version = int(item.properties.publish_version) + 1

            # Save the session
            self._save_session("", next_version, item)


    def publish_files(self, task_settings, item, publish_path):
        """
        Overrides the inherited method to export out session items to the publish_path location.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :param publish_path: The output path to publish files to
        """
        return self._export_mari_session(task_settings, item, publish_path)


    def _export_mari_session(self, task_settings, item, publish_path):
        """
        Exports out an msf file to the specified directory
        """
        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(publish_path)

        try:
            # ensure the publish folder exists:
            ensure_folder_exists(path)

            # Export out an msf file
            mari.session.exportSession(path)

        except Exception as e:
            raise TankError("Failed to publish session item '%s': %s" % (item.name, str(e)))

        self.logger.info("Published session item '%s' to '%s'." % (item.name, path))
        return [path]


    def _get_dependency_ids(self, node=None):
        """
        Find all dependency ids for the current node. If no node specified,
        will return all dependency ids for the session.

        :param node: Optional node to process
        :return: List of upstream dependency ids
        """
        publish_ids = []

        # Collect the geometry publish ids
        for geo_item in self.parent.engine.list_geometry():
            geo = geo_item.get("geo")
            if not geo:
                continue

            # Get the current geo version
            current_version = geo.currentVersion()

            # Get the version metadata
            version_metadata = self.parent.engine.get_shotgun_info(current_version)
            geo_version_publish_id = version_metadata.get("publish_id")
            if not geo_version_publish_id:
                continue

            publish_ids.append(geo_version_publish_id)

        return publish_ids


    def _save_session(self, path, version, item):
        """
        Save the current session.
        """
        self.logger.info("Setting session version to 'v%03d'" % version)
        self.parent.engine.set_project_version(item.properties.project, version)

        # Save the session
        item.properties.project.save()
