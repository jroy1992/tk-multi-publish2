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
import maya.cmds as cmds
import maya.mel as mel
import sgtk
from sgtk.util.filesystem import ensure_folder_exists

HookBaseClass = sgtk.get_hook_baseclass()


class MayaSessionPublishPlugin(HookBaseClass):
    """
    Inherits from SessionPublishPlugin
    """

    SESSION_ITEM_TYPE_FILTERS = ["maya.session"]
    SESSION_ITEM_TYPE_SETTINGS = {
        "maya.session": {
            "publish_type": "Maya Scene",
            "publish_name_template": None,
            "publish_path_template": None
        }
    }

    def _get_dependency_paths(self, node=None):
        """
        Find all dependency paths for the current node. If no node specified,
        will return all dependency paths for the session.

        :param node: Optional node to process
        :return: List of upstream dependency paths
        """

        # default implementation looks for references and
        # textures (file nodes) and returns any paths that
        # match a template defined in the configuration
        ref_paths = set()

        # first let's look at maya references
        ref_nodes = cmds.ls(references=True)
        for ref_node in ref_nodes:
            # get the path:
            ref_path = cmds.referenceQuery(ref_node, filename=True)
            # make it platform dependent
            # (maya uses C:/style/paths)
            ref_path = ref_path.replace("/", os.path.sep)
            if ref_path:
                ref_paths.add(ref_path)

        # now look at file texture nodes
        for file_node in cmds.ls(l=True, type="file"):
            # ensure this is actually part of this session and not referenced
            if cmds.referenceQuery(file_node, isNodeReferenced=True):
                # this is embedded in another reference, so don't include it in
                # the breakdown
                continue

            # get path and make it platform dependent
            # (maya uses C:/style/paths)
            texture_path = cmds.getAttr(
                "%s.fileTextureName" % file_node).replace("/", os.path.sep)
            if texture_path:
                ref_paths.add(texture_path)

        return list(ref_paths)


    def _save_session(self, path, item):
        """
        Save the current session to the supplied path.
        """

        # Maya can choose the wrong file type so we should set it here
        # explicitly based on the extension
        maya_file_type = None
        if path.lower().endswith(".ma"):
            maya_file_type = "mayaAscii"
        elif path.lower().endswith(".mb"):
            maya_file_type = "mayaBinary"

        ensure_folder_exists(os.path.dirname(path))
        cmds.file(rename=path)

        # save the scene:
        if maya_file_type:
            cmds.file(save=True, force=True, type=maya_file_type)
        else:
            cmds.file(save=True, force=True)

        # Save the updated property
        item.properties.path = path
