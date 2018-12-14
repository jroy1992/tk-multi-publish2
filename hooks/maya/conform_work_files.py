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
import glob
import pprint
import traceback
import nuke
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()

_NUKE_OUTPUTS = {
    "Write": "file",
    "WriteGeo": "file",
}

class NukeConformWorkFilesPlugin(HookBaseClass):
    """
    Inherits from ConformWorkFilesPlugin
    """
    def __init__(self, parent, **kwargs):
        """
        Construction
        """
        # call base init
        super(NukeConformWorkFilesPlugin, self).__init__(parent, **kwargs)

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

        if item.type == "file.nuke":
            if not item.properties.path:
                # the session has not been saved before (no path determined).
                # provide a save button. the session will need to be saved before
                # validation will succeed.
                self.logger.warning(
                    "The Nuke script has not been saved.",
                    extra=_get_save_as_action()
                )

        # Run the parent acceptance method
        accept_data = super(NukeConformWorkFilesPlugin, self).accept(task_settings, item)
        if not accept_data.get("accepted"):
            return accept_data

        # If this is a WriteTank node, override task settings from the node
        node = item.properties.get("node")
        if node and node.Class() == "WriteTank":
            if not self.__write_node_app:
                self.logger.error("Unable to process item '%s' without "
                        "the tk-nuke_writenode app!" % item.name)
                accept_data["enabled"] = False
                accept_data["checked"] = False
                return accept_data

            # Overwrite the work_path_template setting for this task
            task_settings["work_path_template"].value = self.__write_node_app.get_node_render_template(node).name

        # return the accepted info
        return accept_data


    def publish(self, task_settings, item):
        """
        Executes the publish logic for the given item and task_settings.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # Just save if this is a nuke session...
        if item.type == "file.nuke":

            # Get work_path_template from the item
            work_file_path = item.properties.work_file_path
            if item.properties.path == work_file_path:
                self.logger.info("Work file(s) already conformed. Skipping")
                return

            _save_session(work_file_path)
            
            # Update path attr to reflect new location
            item.properties.path = work_file_path

            self.logger.info("Work file(s) for item '%s' copied succesfully!" % item.name)

        # Else process the item via the parent class publish
        else:
            super(NukeConformWorkFilesPlugin, self).publish(task_settings, item)


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
        # Update write nodes with the new path
        node = item.properties.get("node")
        if node and node.Class() in _NUKE_OUTPUTS:
            param_name = _NUKE_OUTPUTS[node.Class()]
            node.knob(param_name).setValue(item.properties.work_file_path)


    ############################################################################
    # protected methods

    def _accept_work_path(self, item, work_path_template):
        """
        Compares the item's path with the input work_path_template. If the template
        is not defined or the template and the path match, we do not accept. If the
        path and the template do not match, then we accept the plugin.
        """
        # If this is a WriteTank node, override work_path_template from the node
        node = item.properties.get("node")
        if node and node.Class() == "WriteTank":
            if not self.__write_node_app:
                self.logger.error("Unable to process item '%s' without "
                        "the tk-nuke_writenode app!" % item.name)
                return False

            work_path_template = self.__write_node_app.get_node_render_template(node).name

        # return the parent's response
        return super(NukeConformWorkFilesPlugin, self)._accept_work_path(item, work_path_template)


    def _resolve_item_fields(self, item, task_settings):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        # run the parent method first
        fields = super(NukeConformWorkFilesPlugin, self)._resolve_item_fields(item, task_settings)

        # Get height, width, and output from the node
        node = item.properties.get("node")
        if node:
            fields["width"] = node.width()
            fields["height"] = node.height()
            fields["output"] = node.name()
            
        return fields


def _save_session(path):
    """
    Save the current session to the supplied path.
    """
    nuke.scriptSaveAs(path, True)


def _get_save_as_action():
    """
    Simple helper for returning a log action dict for saving the session
    """
    return {
        "action_button": {
            "label": "Save As...",
            "tooltip": "Save the current session",
            "callback": nuke.scriptSaveAs
        }
    }
