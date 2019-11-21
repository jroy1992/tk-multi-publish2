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
import hou
import sgtk
from sgtk import TankError
from sgtk.templatekey import SequenceKey

HookBaseClass = sgtk.get_hook_baseclass()

# This is a dictionary of file type info that allows the basic collector to
# identify common production file types and associate them with a display name,
# item type, and config icon.
HOUDINI_SESSION_ITEM_TYPES = {
    "houdini.session": {
        "icon_path": "{self}/hooks/icons/houdini.png",
        "type_display": "Houdini Session"
    }
}


class HoudiniSessionCollector(HookBaseClass):
    """
    Collector that operates on the current houdini session. Should inherit from
    the basic collector hook.
    """
    def __init__(self, parent, **kwargs):
        """
        Construction
        """
        # call base init
        super(HoudiniSessionCollector, self).__init__(parent, **kwargs)

        # cache the workfiles app
        self.__workfiles_app = self.parent.engine.apps.get("tk-multi-workfiles2")
        self.houdini_sgtk_outputs = {
            # rops
            hou.ropNodeTypeCategory(): {
                "alembic": "filename",    # alembic cache
                "ifd": "vm_picture",      # mantra render node
            },
        }
        self.houdini_native_outputs = {
            # rops
            hou.ropNodeTypeCategory(): {
                "alembic": "filename",  # alembic cache
                "comp": "copoutput",  # composite
                "ifd": "vm_picture",  # mantra render node
                "opengl": "picture",  # opengl render
                "wren": "wr_picture",  # wren wireframe
            },
        }


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
        schema = super(HoudiniSessionCollector, self).settings_schema
        schema["Item Types"]["default_value"].update(HOUDINI_SESSION_ITEM_TYPES)
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
        Analyzes the current Houdini session and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        items = []

        # create an item representing the current houdini session
        session_item = self.collect_current_houdini_session(settings, parent_item)
        items.append(session_item)

        # collect other, non-toolkit outputs to present for publishing
        items.extend(self.collect_node_outputs(settings, session_item))

        # if we have work path templates, collect matching files to publish
        for work_template in settings["Work File Templates"].value:
            items.extend(self.collect_work_files(settings, session_item, work_template))

        # Return the list of items
        return items


    def collect_current_houdini_session(self, settings, parent_item):
        """
        Creates an item that represents the current houdini session.

        :param dict settings: Configured settings for this collector
        :param parent_item: Parent Item instance

        :returns: Item of type houdini.session
        """

        # get the path to the current file
        file_path = hou.hipFile.path()
        if not file_path:
            # the session has not been saved before (no path determined).
            # provide a save button. the session will need to be saved before
            # validation will succeed.
            self.logger.warning(
                "The Houdini scene has not been saved.",
                extra=self._get_save_as_action()
            )

        # Define the item's properties
        properties = {}

        session_item = self._add_file_item(settings,
                                           parent_item,
                                           file_path,
                                           False,
                                           None,
                                           "Current Houdini Session",
                                           "houdini.session",
                                           parent_item.context,
                                           properties)

        self.logger.info("Collected item: %s" % session_item.name)
        return session_item


    def collect_node_outputs(self, settings, parent_item):
        """
        Creates items for known output nodes

        :param dict settings: Configured settings for this collector
        :param parent_item: The parent item for any write geo nodes collected
        """
        items = []

        # collect nodes if the app is installed
        for node in self.houdini_sgtk_outputs[hou.ropNodeTypeCategory()]:
            setattr(self, "_{}_nodes_collected".format(node), False)
            collect_method = getattr(self, "collect_tk_{}nodes".format(node))
            items.extend(collect_method(settings, parent_item))

        for node_category in self.houdini_native_outputs:
            for node_type in self.houdini_native_outputs[node_category]:

                if self.houdini_sgtk_outputs.get(node_category, {}).get(node_type):
                    if getattr(self, "_{}_nodes_collected".format(node_type)):
                        self.logger.debug(
                            "Skipping regular {0} node collection since tk "
                            "{0} nodes were collected. ".format(node_type)
                        )
                        continue

                path_parm_name = self.houdini_native_outputs[node_category][node_type]

                # get all the nodes for the category and type
                nodes = hou.nodeType(node_category, node_type).instances()

                # iterate over each node
                for node in nodes:

                    # get the evaluated path parm value
                    file_path = node.parm(path_parm_name).eval()

                    # ensure the output path exists
                    if not os.path.exists(file_path):
                        continue

                    self.logger.info(
                        "Processing %s node: %s" % (node.type().name(), node.name()))

                    # allow the base class to collect and create the item. it
                    # should know how to handle the output path
                    item = self._collect_file(settings, parent_item, file_path)

                    # the item has been created. update the display name to
                    # include the node path to make it clear to the user how it
                    # was collected within the current session.
                    item.name = "%s (%s)" % (node.type().name(), node.name())

                    # Store a reference to the originating node
                    item.properties.node = node

                    # Add item to the list
                    items.append(item)

        return items


    def collect_tk_alembicnodes(self, settings, parent_item):
        """
        Checks for an installed `tk-houdini-alembicnode` app. If installed, will
        search for instances of the node in the current session and create an
        item for each one with an output on disk.

        :param dict settings: Configured settings for this collector
        :param parent_item: The parent item for any write geo nodes collected
        """
        items = []

        publisher = self.parent
        engine = publisher.engine

        alembicnode_app = engine.apps.get("tk-houdini-alembicnode")
        if not alembicnode_app:
            self.logger.debug(
                "The tk-houdini-alembicnode app is not installed. "
                "Will not attempt to collect those nodes."
            )
            return items

        try:
            tk_alembic_nodes = alembicnode_app.get_nodes()
        except AttributeError:
            self.logger.warning(
                "Unable to query the session for tk-houdini-alembicnode "
                "instances. It looks like perhaps an older version of the "
                "app is in use which does not support querying the nodes. "
                "Consider updating the app to allow publishing their outputs."
            )
            return items

        for node in tk_alembic_nodes:

            out_path = alembicnode_app.get_output_path(node)

            if not os.path.exists(out_path):
                continue

            self.logger.info(
                "Processing sgtk_alembic node: %s" % (node.name(),))

            # allow the base class to collect and create the item. it
            # should know how to handle the output path
            item = self._collect_file(settings, parent_item, out_path)

            # the item has been created. update the display name to
            # include the node path to make it clear to the user how it
            # was collected within the current session.
            item.name = "%s (%s)" % (node.type().name(), node.name())

            # Store a reference to the originating node
            item.properties.node = node

            # Add item to the list
            items.append(item)

            self._alembic_nodes_collected = True

        return items


    def collect_tk_ifdnodes(self, settings, parent_item):
        """
        Checks for an installed `tk-houdini-mantranode` app. If installed, will
        search for instances of the node in the current session and create an
        item for each one with an output on disk.

        :param dict settings: Configured settings for this collector
        :param parent_item: The parent item for any write geo nodes collected
        """
        items = []

        publisher = self.parent
        engine = publisher.engine

        mantranode_app = engine.apps.get("tk-houdini-mantranode")
        if not mantranode_app:
            self.logger.debug(
                "The tk-houdini-mantranode app is not installed. "
                "Will not attempt to collect those nodes."
            )
            return items

        try:
            tk_mantra_nodes = mantranode_app.get_nodes()
        except AttributeError:
            self.logger.warning(
                "Unable to query the session for tk-houdini-mantranode "
                "instances. It looks like perhaps an older version of the "
                "app is in use which does not support querying the nodes. "
                "Consider updating the app to allow publishing their outputs."
            )
            return items

        for node in tk_mantra_nodes:

            out_path = mantranode_app.get_output_path(node)

            if not os.path.exists(out_path):
                continue

            self.logger.info(
                "Processing sgtk_mantra node: %s" % (node.name(),))

            # allow the base class to collect and create the item. it
            # should know how to handle the output path
            item = self._collect_file(settings, parent_item, out_path)

            # the item has been created. update the display name to
            # include the node path to make it clear to the user how it
            # was collected within the current session.
            item.name = "%s (%s)" % (node.type().name(), node.name())

            # Store a reference to the originating node
            item.properties.node = node

            # Add item to the list
            items.append(item)

            self._ifd_nodes_collected = True

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
            if isinstance(key, SequenceKey) and key.name in fields:
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
        publisher = self.parent
        engine = publisher.engine

        node = item.properties.get("node")
        if node and node.type().name() in ("sgtk_alembic", "sgtk_mantra"):
            if node.type().name() == "sgtk_mantra":
                write_node_app = engine.apps.get("tk-houdini-mantranode")
            elif node.type().name() == "sgtk_alembic":
                write_node_app = engine.apps.get("tk-houdini-alembicnode")

            if write_node_app:
                # Get work_path_template from the write_node app and update fields
                return write_node_app.get_work_file_template().name
            else:
                self.logger.error("Unable to process item '%s' without "
                        "the tk-houdini_writenode app!" % item.name)

        # If this is a houdini session and we have the workfiles app defined...
        elif item.type == "houdini.session" and self.__workfiles_app:
            # Get work_path_template from the workfiles app for the item's context
            # Note: this needs to happen here instead of during item initialization
            # since the path may change if the context changes
            return self.__workfiles_app.get_work_template(item.context).name

        return super(HoudiniSessionCollector, self)._resolve_work_path_template(settings, item)


    def _resolve_item_fields(self, settings, item):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        # Now run the parent resolve method
        fields = super(HoudiniSessionCollector, self)._resolve_item_fields(settings, item)

#        node = item.properties.get("node")
#        if node and node.type().name() in ("sgtk_mantra", "ifd"):
#            # If not defined, get the height and width from the cam_node
#            if "width" not in fields or "height" not in fields:
#                if node.evalParm("override_camerares"):
#                    fields["width"] = node.evalParm("res_overridex")
#                    fields["height"] = node.evalParm("res_overridey")
#                else:
#                    cam_name = node.evalParm("camera")
#                    if cam_name:
#                        cam_node = hou.node(cam_name)
#                        if cam_node:
#                            fields["width"] = cam_node.evalParm("resx")
#                            fields["height"] = cam_node.evalParm("resy")

        return fields


def _session_path():
    """
    Return the path to the current session
    :return:
    """

    # Houdini always returns a file path, even for new sessions. We key off the
    # houdini standard of "untitled.hip" to indicate that the file has not been
    # saved.
    if hou.hipFile.name() == "untitled.hip":
        return None

    return hou.hipFile.path()


def _save_session(path):
    """
    Save the current session to the supplied path.
    """
    # We need to flip the slashes on Windows to avoid a bug in Houdini. If we don't
    # the next Save As dialog will have the filename box populated with the complete
    # file path.
    hou.hipFile.save(file_name=path.replace("\\", "/").encode("utf-8"))
