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
import itertools
import nuke
import sgtk
from sgtk.util.filesystem import ensure_folder_exists

HookBaseClass = sgtk.get_hook_baseclass()


# A list of input node types to check as dependencies
_NUKE_INPUTS = ("Read", "ReadGeo2", "Camera2")

class NukePublishSessionPlugin(HookBaseClass):
    """
    Inherits from SessionPublishPlugin
    """

    SESSION_ITEM_TYPE_FILTERS = ["nuke.session"]
    SESSION_ITEM_TYPE_SETTINGS = {
        "nuke.session": {
            "publish_type": "Nuke Script",
            "publish_name_template": None,
            "publish_path_template": None
        }
    }

    def _get_dependency_paths(self, task_settings, item, node=None):
        """
        Find all dependency paths for the current node. If no node specified,
        will return all dependency paths for the nuke script.

        :param node: Optional node to process
        :return: List of upstream dependency paths
        """
        publisher = self.parent
        dependency_paths = []

        if node:
            allnodes = nuke.allNodes()
            visited = {nodes: 0 for nodes in allnodes}
            # Collect all upstream nodes to specified node
            dep_nodes = []
            input_nodes = _collect_dep_nodes(node, visited, dep_nodes)
        else:
            # Collect all nodes in this nuke script
            # dep_nodes = nuke.allNodes()
            input_node_lists = [nuke.allNodes(node) for node in _NUKE_INPUTS]
            input_nodes = list(itertools.chain(*(node for node in input_node_lists)))

        # Only process nodes that match one of the specified input types
        # input_nodes = [node for node in dep_nodes if node.Class() in _NUKE_INPUTS]

        # figure out all the inputs to the node and pass them as dependency
        # candidates together with keeping track of what all file paths have been visited
        file_path_visited = {}

        for dep_node in input_nodes:
            if dep_node['disable'].value() == 1:
                continue
            file_path = dep_node.knob('file').evaluate()
            if not file_path:
                continue

            file_path = sgtk.util.ShotgunPath.normalize(file_path)
            if file_path in file_path_visited:
                continue
            else:
                # Keeping track of visited paths
                file_path_visited[file_path] = 1
                # Check if the input path contains a frame number
                seq_path = publisher.util.get_frame_sequence_path(file_path)
                if seq_path:
                    # If so, then use the path with the frame number replaced with the frame spec
                    file_path = seq_path

                dependency_paths.append(file_path)

        return dependency_paths


    def _save_session(self, path, version, item):
        """
        Save the current session to the supplied path.
        """
        ensure_folder_exists(os.path.dirname(path))
        nuke.scriptSaveAs(path, True)

        # Save the updated property
        item.properties.path = path


def _collect_dep_nodes(node, visited, dep_nodes):
    """
    For each specified node, traverse the node graph and get any associated upstream nodes.

    :param nodes: List of nodes to process
    :return: List of upstream dependency nodes
    """
    # dependency_list = list(itertools.chain(*(node.dependencies() for node in nodes)))
    # if dependency_list:
    #     depends = _collect_dep_nodes(dependency_list)
    #     for item in depends:
    #         nodes.append(item)
    #
    # # Remove duplicates
    # return list(set(nodes))
    if visited[node] == 0:
        if node.Class() in _NUKE_INPUTS and (node['disable'].value() == 0):
            dep_nodes.append(node)
        # set visited to 1 for the node so as not to revisit
        visited[node] = 1
        dep = node.dependencies()
        if dep:
            for item in dep:
                _collect_dep_nodes(item, visited, dep_nodes)
    return dep_nodes
