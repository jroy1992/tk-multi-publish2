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

HookBaseClass = sgtk.get_hook_baseclass()


# A list of input node types to check as dependencies
_NUKE_INPUTS = ("Read", "ReadGeo2", "Camera2", "DeepRead")

class NukePublishFilesPlugin(HookBaseClass):
    """
    Inherits from PublishFilesPlugin
    """
    def __init__(self, parent, **kwargs):
        """
        Construction
        """
        # call base init
        super(NukePublishFilesPlugin, self).__init__(parent, **kwargs)

        # import writenode constants
        tk_nuke_writenode = self.parent.import_module("tk_nuke_writenode")
        self.sg_write_node_classes = tk_nuke_writenode.TankWriteNodeHandler.NUKE_TO_SG_CLASS_MAPPING.values()

        # cache the write node app
        self.__write_node_app = self.parent.engine.apps.get("tk-nuke-writenode")


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

        # Run the parent acceptance method
        accept_data = super(NukePublishFilesPlugin, self).accept(task_settings, item)
        if not accept_data.get("accepted"):
            return accept_data

        # If this is a WriteTank node, override task settings from the node
        node = item.properties.get("node")
        if node and node.Class() in self.sg_write_node_classes:
            if not self.__write_node_app:
                self.logger.error("Unable to process item '%s' without "
                        "the tk-nuke_writenode app!" % item.name)
                accept_data["enabled"] = False
                accept_data["checked"] = False
                return accept_data

            # Overwrite the publish_type and publish_path_template settings for this task
            task_settings["publish_type"].value = self.__write_node_app.get_node_tank_type(node)
            task_settings["publish_path_template"].value = self.__write_node_app.get_node_publish_template(node).name

        # return the accepted info
        return accept_data


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

        # If this is a WriteTank node, check to see if the node path is currently locked
        node = item.properties.get("node")
        if node and node.Class() in self.sg_write_node_classes:
            if self.__write_node_app.is_node_render_path_locked(node):
                # renders for the write node can't be published - trying to publish
                # will result in an error in the publish hook!
                self.logger.error("The render path is currently locked and "
                        "does not match the current Work Area.")
                return False

        return super(NukePublishFilesPlugin, self).validate(task_settings, item)


    def publish(self, task_settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        node = item.properties.get("node")
        if node:
            # Store any node dependencies
            item.properties.publish_dependency_paths = self._get_dependency_paths(node)

        super(NukePublishFilesPlugin, self).publish(task_settings, item)


    def _get_dependency_paths(self, node=None):
        """
        Find all dependency paths for the current node. If no node specified,
        will return all dependency paths for the nuke script.

        :param node: Optional node to process
        :return: List of upstream dependency paths
        """
        publisher = self.parent
        dependency_paths = set()

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
        # candidates
        for dep_node in input_nodes:
            if dep_node['disable'].value() == 1:
                continue
            file_path = dep_node.knob('file').evaluate()
            if not file_path:
                continue

            file_path = sgtk.util.ShotgunPath.normalize(file_path)

            # Check if the input path contains a frame number
            seq_path = publisher.util.get_frame_sequence_path(file_path)
            if seq_path:
                # If so, then use the path with the frame number replaced with the frame spec
                file_path = seq_path

            dependency_paths.add(file_path)

        return list(dependency_paths)


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
