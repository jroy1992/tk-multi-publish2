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
import hou
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

# A list of input node types to check as dependencies
# A dict of dicts organized by category, type and output file parm
_HOUDINI_INPUTS = {
    # sops
    hou.sopNodeTypeCategory(): {
        "alembic": "fileName",    # alembic cache
    },
}

class HoudiniSessionPublishPlugin(HookBaseClass):
    """
    Inherits from SessionPublishPlugin
    """

    SESSION_ITEM_TYPE_FILTERS = ["houdini.session"]
    SESSION_ITEM_TYPE_SETTINGS = {
        "houdini.session": {
            "publish_type": "Houdini Scene",
            "publish_name_template": None,
            "publish_path_template": None
        }
    }

    def _get_dependency_paths(self, node=None):
        """
        Find all dependency paths for the current node. If no node specified,
        will return all dependency paths for the houdini scene.

        :param node: Optional node to process
        :return: List of upstream dependency paths
        """
        publisher = self.parent
        dependency_paths = []

        input_nodes = []
        if node:
            # Collect all upstream nodes to specified node
            input_nodes = node.inputAncestors()

        else:
            # Collect all input nodes in this houdini session
            for node_category in _HOUDINI_INPUTS:
                for node_type in _HOUDINI_INPUTS[node_category]:
                    # get all the nodes for the category and type
                    input_nodes.extend(hou.nodeType(node_category, node_type).instances())

        # figure out all the inputs to the node and pass them as dependency
        # candidates
        for dep_node in input_nodes:
            if dep_node.isBypassed():
                continue

            node_type = dep_node.type().name()
            node_category = dep_node.type().category().name()

            # Ensure this is a matching input node type
            if node_category not in _HOUDINI_INPUTS or \
               node_type not in _HOUDINI_INPUTS[node_category]:
                continue

            path_parm_name = _HOUDINI_INPUTS[node_category][node_type]

            file_path = dep_node.evalParm(path_parm_name)
            if not file_path:
                continue

            file_path = sgtk.util.ShotgunPath.normalize(file_path)

            # Check if the input path contains a frame number
            seq_path = publisher.util.get_frame_sequence_path(file_path)
            if seq_path:
                # If so, then use the path with the frame number replaced with the frame spec
                file_path = seq_path

            dependency_paths.append(file_path)

        return dependency_paths


    def _save_session(self, path, item):
        """
        Save the current session to the supplied path.
        """
        # We need to flip the slashes on Windows to avoid a bug in Houdini. If we don't
        # the next Save As dialog will have the filename box populated with the complete
        # file path.
        hou.hipFile.save(file_name=path.replace("\\", "/").encode("utf-8"))

        # Save the updated property
        item.properties.path = path
