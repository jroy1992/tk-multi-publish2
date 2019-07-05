# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import copy
import os
import nuke
import sgtk
from sgtk import TankError
from sgtk.templatekey import SequenceKey
from sgtk.platform.qt import QtGui

HookBaseClass = sgtk.get_hook_baseclass()

# This is a dictionary of file type info that allows the basic collector to
# identify common production file types and associate them with a display name,
# item type, and config icon.
NUKE_ITEM_TYPES = {
    "nuke.session": {
        "icon_path": "{self}/hooks/icons/nuke.png",
        "type_display": "Nuke Session"
    },
    "nukestudio.project": {
        "icon_path": "{self}/hooks/icons/nukestudio.png",
        "type_display": "NukeStudio Project"
    }
}

# A look up of node types to parameters for finding outputs to publish
_NUKE_OUTPUTS = {
    "WriteTank": "file",
    "DeepWriteTank": "file",
    "DeepWrite": "file",
}


class NukeSessionCollector(HookBaseClass):
    """
    Collector that operates on the current nuke/nukestudio session. Should
    inherit from the basic collector hook.
    """
    def __init__(self, parent, **kwargs):
        """
        Construction
        """
        # call base init
        super(NukeSessionCollector, self).__init__(parent, **kwargs)

        # import writenode constants
        tk_nuke_writenode = self.parent.import_module("tk_nuke_writenode")
        self.sg_write_node_classes = tk_nuke_writenode.TankWriteNodeHandler.NUKE_TO_SG_CLASS_MAPPING.values()

        # cache the write node and workfiles apps
        self.__write_node_app = self.parent.engine.apps.get("tk-nuke-writenode")
        self.__workfiles_app = self.parent.engine.apps.get("tk-multi-workfiles2")


    @property
    def settings_schema(self):
        """
        Dictionary defining the settings that this collector expects to receive
        through the settings parameter in the process_current_session and
        process_file methods.

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
        schema = super(NukeSessionCollector, self).settings_schema
        schema["Item Types"]["default_value"].update(NUKE_ITEM_TYPES)
        schema["Work File Templates"] = {
            "type": "list",
            "values": {
                "type": "template",
                "description": "",
                "fields": "context, *"
            },
            "default_value": [],
            "allows_empty": True,
            "description": "A list of templates to use to search for work files."
        }
        return schema


    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current session open in Nuke/NukeStudio and parents a
        subtree of items under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        items = []

        publisher = self.parent
        engine = publisher.engine

        if hasattr(engine, "studio_enabled") and engine.studio_enabled:
            # running nuke studio.
            items.extend(self.collect_current_nukestudio_session(settings, parent_item))

            # since we're in NS, any additional collected outputs will be
            # parented under the root item
            session_item = parent_item
        else:
            # running nuke. ensure additional collected outputs are parented
            # under the session
            session_item = self.collect_current_nuke_session(settings, parent_item)

            # Add session_item to the list
            items.append(session_item)

        # Also collect any output node items
        items.extend(self.collect_node_outputs(settings, session_item))

        # if we have work path templates, collect matching files to publish
        for work_template in settings["Work File Templates"].value:
            items.extend(self.collect_work_files(settings, session_item, work_template))

        # Return the list of items
        return items


    def collect_current_nuke_session(self, settings, parent_item):
        """
        Analyzes the current session open in Nuke and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        # get the current path
        file_path = _session_path()
        if not file_path:
            # the session has not been saved before (no path determined).
            # provide a save button. the session will need to be saved before
            # validation will succeed.
            self.logger.warning(
                "The Nuke script has not been saved.",
                extra=self._get_save_as_action()
            )

        # Define the item's properties
        properties = {}

        session_item = self._add_file_item(settings,
                                           parent_item,
                                           file_path,
                                           False,
                                           None,
                                           "Current Nuke Session",
                                           "nuke.session",
                                           parent_item.context,
                                           properties)

        self.logger.info("Collected item: %s" % session_item.name)
        return session_item


    def collect_current_nukestudio_session(self, settings, parent_item):
        """
        Analyzes the current session open in NukeStudio and parents a subtree of
        items under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """

        # import here since the hooks are imported into nuke and nukestudio.
        # hiero module is only available in later versions of nuke
        import hiero.core

        active_project = hiero.ui.activeSequence().project()

        items = []
        for project in hiero.core.projects():

            # get the current path
            file_path = project.path()
            if not file_path:
                # the project has not been saved before (no path determined).
                # provide a save button. the project will need to be saved before
                # validation will succeed.
                self.logger.warning(
                    "The Nuke Studio project '%s' has not been saved." %
                    (project.name()),
                    extra=self._get_save_as_action(project)
                )

            # Define the item's properties
            properties = {}

            # add the project object to the properties so that the publish
            # plugins know which open project to associate with this item
            properties["project"] = project

            # create the session item for the publish hierarchy
            project_item = self._add_file_item(settings,
                                               parent_item,
                                               project.path(),
                                               False,
                                               None,
                                               project.name(),
                                               "nukestudio.project",
                                               parent_item.context,
                                               properties)

            self.logger.info(
                "Collected Nuke Studio project: %s" % (project_item.name,))
            items.append(project_item)

            # enable the active project and expand it. other projects are
            # collapsed and disabled.
            if active_project and active_project.guid() == project.guid():
                project_item.expanded = True
                project_item.checked = True
                project_item.properties.active = True
            elif active_project:
                # there is an active project, but this isn't it. collapse and
                # disable this item
                project_item.expanded = False
                project_item.checked = False

        return items


    def collect_node_outputs(self, settings, parent_item):
        """
        Scan known output node types in the session and see if they reference
        files that have been written to disk.

        :param dict settings: Configured settings for this collector
        :param parent_item: The parent item for any write geo nodes collected
        """
        items = []

        publisher = self.parent

        # iterate over all the known output types
        for node_type in _NUKE_OUTPUTS:

            # get all the instances of the node type
            all_nodes_of_type = [n for n in nuke.allNodes()
                if n.Class() == node_type]

            # iterate over each instance
            for node in all_nodes_of_type:

                # Skip the node if its disabled
                if node["disable"].value():
                    continue

                self.logger.info(
                    "Processing %s node: %s" % (node_type, node.name()))

                if node_type in self.sg_write_node_classes:

                    if not self.__write_node_app:
                        self.logger.error("Unable to process node '%s' without "
                                "the tk-nuke_writenode app!" % node.name())
                        continue

                    # Get the file path and sequence files from the node itself
                    file_path = self.__write_node_app.get_node_render_path(node)
                    thumbnail = self.__write_node_app.generate_node_thumbnail(node)

                else:
                    # evaluate the output path parameter which may include frame
                    # expressions/format
                    param_name = _NUKE_OUTPUTS[node_type]
                    file_path = node[param_name].evaluate()
                    thumbnail = None


                # Collect the item if we have a file_path defined
                if file_path:

                    # Call the parent _collect_file method
                    item = self._collect_file(settings, parent_item, file_path)
                    if not item:
                        continue

                    # the item has been created. update the display name to include
                    # the nuke node to make it clear to the user how it was
                    # collected within the current session. also, prepend nukesession
                    # to the item type so we can process it by the nuke-specific publish
                    item.name = "%s (%s)" % (node.Class(), node.name())

                    # Store a reference to the originating node
                    item.properties.node = node

                    if thumbnail:
                        item.set_thumbnail_from_path(thumbnail)

                    # Add item to the list
                    items.append(item)

        return items


    def collect_work_files(self, settings, parent_item, work_template):
        """
        Creates items for files matching the work path template
        """
        items = []
        try:
            work_paths = self._get_work_paths(parent_item, work_template)
            for work_path in work_paths:
                item = self._collect_file(settings, parent_item, work_path)
                if not item:
                    continue

				# Track the current work template being processed
                item.properties.work_path_template = work_template

                # Add the item to the list
                items.append(item)

        except Exception as e:
            self.logger.warning("%s. Skipping..." % str(e))

        return items


    def _get_work_paths(self, parent_item, work_path_template):
        """
        Get paths matching the work path template using the supplied item's fields.

        :param parent_item: The item to determine the work path for
        :param work_path_template: The template string to resolve

        :return: A list of paths matching the resolved work path template for
            the supplied item

        Extracts the work path via the configured work templates
        if possible.
        """

        publisher = self.parent

        # Start with the item's fields, minus extension
        fields = copy.deepcopy(parent_item.properties.get("fields", {}))
        fields.pop("extension", None)

        # also collect sequence files
        for key in self.sgtk.template_keys.values():
            if isinstance(key, SequenceKey):
                fields.pop(key.name)

        work_tmpl = publisher.get_template_by_name(work_path_template)
        if not work_tmpl:
            # this template was not found in the template config!
            raise TankError("The Template '%s' does not exist!" % work_path_template)

        # First get the fields from the context
        try:
            fields.update(parent_item.context.as_template_fields(work_tmpl))
        except TankError:
            self.logger.warning(
                "Unable to get context fields for work_path_template.")

        # Get the paths from the template using the known fields
        self.logger.info(
            "Searching for file(s) matching: '%s'" % work_path_template,
            extra={
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": "Template: %s\nFields: %s" % (work_tmpl, fields)
                }
            }
        )
        return self.sgtk.abstract_paths_from_template(work_tmpl,
                                                      fields,
                                                      skip_missing_optional_keys=True)


    def _resolve_work_path_template(self, settings, item):
        """
        Resolve work_path_template from the collector settings for the specified item.

        :param dict settings: Configured settings for this collector
        :param item: The Item instance
        :return: Name of the template.
        """
        node = item.properties.get("node")
        if node and node.Class() in self.sg_write_node_classes:
            if self.__write_node_app:
                # Get work_path_template from the write_node app and update fields
                return self.__write_node_app.get_node_render_template(node).name
            else:
                self.logger.error("Unable to process item '%s' without "
                        "the tk-nuke_writenode app!" % item.name)

        # If this is a nuke session and we have the workfiles app defined...
        elif item.type == "nuke.session" and self.__workfiles_app:
            # Get work_path_template from the workfiles app for the item's context
            # Note: this needs to happen here instead of during item initialization
            # since the path may change if the context changes
            return self.__workfiles_app.get_work_template(item.context).name

        return super(NukeSessionCollector, self)._resolve_work_path_template(settings, item)


    def _resolve_item_fields(self, settings, item):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        # Now run the parent resolve method
        fields = super(NukeSessionCollector, self)._resolve_item_fields(settings, item)

        node = item.properties.get("node")
        if node:
            # If not defined, get the height and width from the node
            if "width" not in fields or "height" not in fields:
                fields["width"] = node.width()
                fields["height"] = node.height()

        return fields


    def _get_save_as_action(self, project=None):
        """
        Simple helper for returning a log action dict for saving the session
        """
        # default save callback
        if project:
            callback = lambda: _project_save_as(project)
        else:
            callback = nuke.scriptSaveAs

        # if workfiles2 is configured, use that for file save
        if self.__workfiles_app:
            callback = self.__workfiles_app.show_file_save_dlg

        return {
            "action_button": {
                "label": "Save As...",
                "tooltip": "Save the current session",
                "callback": callback
            }
        }


def _session_path():
    """
    Return the path to the current session
    :return:
    """
    root_name = nuke.root().name()
    return None if root_name == "Root" else root_name


def _project_save_as(project):
    """
    A save as wrapper for the current session.

    :param path: Optional path to save the current session as.
    """
    # TODO: consider moving to engine

    # import here since the hooks are imported into nuke and nukestudio.
    # hiero module is only available in later versions of nuke
    import hiero

    # nuke studio/hiero don't appear to have a "save as" dialog accessible via
    # python. so open our own Qt file dialog.
    file_dialog = QtGui.QFileDialog(
        parent=hiero.ui.mainWindow(),
        caption="Save As",
        directory=project.path(),
        filter="Nuke Studio Files (*.hrox)"
    )
    file_dialog.setLabelText(QtGui.QFileDialog.Accept, "Save")
    file_dialog.setLabelText(QtGui.QFileDialog.Reject, "Cancel")
    file_dialog.setOption(QtGui.QFileDialog.DontResolveSymlinks)
    file_dialog.setOption(QtGui.QFileDialog.DontUseNativeDialog)
    if not file_dialog.exec_():
        return
    path = file_dialog.selectedFiles()[0]
    project.saveAs(path)
