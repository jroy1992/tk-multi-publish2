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
from sgtk.util.filesystem import ensure_folder_exists

HookBaseClass = sgtk.get_hook_baseclass()


SESSION_ITEM_TYPE_FILTERS = ["nukestudio.project"]
SESSION_ITEM_TYPE_SETTINGS = {
    "nukestudio.project": {
        "publish_type": "NukeStudio Project",
        "publish_name_template": None,
        "publish_path_template": None
    }
}

class NukeStudioProjectPublishPlugin(HookBaseClass):
    """
    Inherits from SessionPublishPlugin
    """

    def _get_dependency_paths(self, node=None):
        """
        Find all dependency paths for the current node. If no node specified,
        will return all dependency paths for the session.

        :param node: Optional node to process
        :return: List of upstream dependency paths
        """
        return None


    def _get_dependency_ids(self, node=None):
        """
        Find all dependency ids for the current node. If no node specified,
        will return all dependency ids for the session.

        :param node: Optional node to process
        :return: List of upstream dependency ids
        """
        return None


    def _save_session(self, path, item):
        """
        Save the current session to the supplied path.
        """
        # Nuke Studio won't ensure that the folder is created when saving, so we must make sure it exists
        ensure_folder_exists(os.path.dirname(path))
        item.properties.project.saveAs(path)
