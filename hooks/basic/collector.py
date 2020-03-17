# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import fnmatch
import mimetypes
import os
import pprint
import sgtk
from sgtk import TankError
from sgtk.platform.qt import QtCore, QtGui

HookBaseClass = sgtk.get_hook_baseclass()


# This is a dictionary of file type info that allows the basic collector to
# identify common production file types and associate them with a display name,
# item type, and config icon.
DEFAULT_ITEM_TYPES = {
    "file.alembic": {
        "extensions": ["abc"],
        "icon_path": "{self}/hooks/icons/alembic.png",
        "type_display": "Alembic Cache"
    },
    "file.3dsmax": {
        "extensions": ["max"],
        "icon_path": "{self}/hooks/icons/3dsmax.png",
        "type_display": "3dsmax Scene"
    },
    "file.houdini": {
        "extensions": ["hip", "hipnc"],
        "icon_path": "{self}/hooks/icons/houdini.png",
        "type_display": "Houdini Scene"
    },
    "file.maya": {
        "extensions": ["ma", "mb"],
        "icon_path": "{self}/hooks/icons/maya.png",
        "type_display": "Maya Scene"
    },
    "file.motionbuilder": {
        "extensions": ["fbx"],
        "icon_path": "{self}/hooks/icons/motionbuilder.png",
        "type_display": "Motion Builder FBX",
    },
    "file.nuke": {
        "extensions": ["nk"],
        "icon_path": "{self}/hooks/icons/nuke.png",
        "type_display": "Nuke Script"
    },
    "file.nukestudio": {
        "extensions": ["hrox"],
        "icon_path": "{self}/hooks/icons/nukestudio.png",
        "type_display": "NukeStudio Project"
    },
    "file.photoshop": {
        "extensions": ["psd", "psb"],
        "icon_path": "{self}/hooks/icons/photoshop.png",
        "type_display": "Photoshop Image"
    },
    "file.render": {
        "extensions": ["dpx", "exr"],
        "icon_path": "{self}/hooks/icons/image.png",
        "type_display": "Rendered Image"
    },
    "file.deep_render": {
        "extensions": ["exr", "dtex"],
        "icon_path": "{self}/hooks/icons/image.png",
        "type_display": "Deep Rendered Image"
    },
    "file.texture": {
        "extensions": ["tif", "tiff", "tx", "tga", "dds", "rat"],
        "icon_path": "{self}/hooks/icons/texture.png",
        "type_display": "Texture Image"
    },
    "file.image": {
        "extensions": ["jpeg", "jpg", "png"],
        "icon_path": "{self}/hooks/icons/image.png",
        "type_display": "Image"
    },
    "file.video": {
        "extensions": ["mov", "mp4"],
        "icon_path": "{self}/hooks/icons/video.png",
        "type_display": "Movie"
    }
}


class PopupItemTypesListUI(object):

    """
    If matched_work_path_template is None, then pops up UI with available item_types, sothat user can choose
    item_type.
    Ex: [exr] file type
        We have multiple item_type for exr, if matched_work_path_template is None then
        UI will pop out listing out item_type selection.
    """
    def __init__(self, engine, path, item_types):
        self.engine = engine
        self.path = path
        self.item_types = item_types
        self.selected_item = None
        self.dialog = None
        self.items_list_widget = None
        self.create_ui()

    def create_ui(self):
        self.dialog = QtGui.QDialog()
        self.dialog.setWindowTitle('Select Item Type')
        self.dialog.setMinimumWidth(300)
        self.dialog.setMinimumHeight(100)
        self.dialog.setWindowFlags(QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint)
        self.dialog.keyPressEvent = self.key_press_event
        main_layout = QtGui.QVBoxLayout(self.dialog)

        qtwidgets = sgtk.platform.framework.load_framework(
            self.engine, self.engine.context, self.engine.env, "tk-framework-qtwidgets_v2.x.x")
        elided_label = qtwidgets.import_module("elided_label")

        path_label = elided_label.ElidedLabel()
        path_label.setText("File Name: {}".format(self.path))
        main_layout.addWidget(path_label)
        # create list widget with items
        self.items_list_widget = QtGui.QListWidget()
        self.items_list_widget.addItems(self.item_types)
        main_layout.addWidget(self.items_list_widget)
        # select first item
        self.items_list_widget.setCurrentRow(0)
        # create "OK" button
        ok_button = QtGui.QPushButton("OK")
        ok_button.clicked.connect(self.get_selected_item)
        main_layout.addWidget(ok_button)
        self.dialog.exec_()

    def get_selected_item(self):
        """
        get selected file_type from UI
        :return:
        """
        self.dialog.close()
        self.selected_item = self.items_list_widget.currentItem().text()

    def key_press_event(self, keyEvent):
        """
        This function will skip Escape key from closing UI
        :param keyEvent:
        :return:
        """
        if keyEvent.key() != QtCore.Qt.Key_Escape:
            QtGui.QDialog.keyPressEvent(self.dialog, keyEvent)


class FileCollectorPlugin(HookBaseClass):
    """
    A basic collector that handles files and general objects.

    This collector hook is used to collect individual files that are browsed or
    dragged and dropped into the Publish2 UI. It can also be subclassed by other
    collectors responsible for creating items for a file to be published such as
    the current Maya session file.

    This plugin centralizes the logic for collecting a file, including
    determining how to display the file for publishing (based on the file
    extension).

    In addition to creating an item to publish, this hook will set the following
    properties on the item::

        path - The path to the file to publish. This could be a path
            representing a sequence of files (including a frame specifier).

        sequence_paths - If the item represents a collection of files, the
            plugin will populate this property with a list of files matching
            "path".

    """

    @property
    def common_file_info(self):
        """
        A dictionary of file type info that allows the basic collector to
        identify common production file types and associate them with a display
        name, item type, and config icon.

        The dictionary returned is of the form::

            {
                <Publish Type>: {
                    "extensions": [<ext>, <ext>, ...],
                    "icon_path": <icon path>,
                    "item_type": <item type>
                },
                <Publish Type>: {
                    "extensions": [<ext>, <ext>, ...],
                    "icon_path": <icon path>,
                    "item_type": <item type>
                },
                ...
            }

        See the collector source to see the default values returned.

        Subclasses can override this property, get the default values via
        ``super``, then update the dictionary as necessary by
        adding/removing/modifying values.
        """

        if not hasattr(self, "_common_file_info"):

            # do this once to avoid unnecessary processing
            self._common_file_info = DEFAULT_ITEM_TYPES

        return self._common_file_info

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
        schema = super(FileCollectorPlugin, self).settings_schema
        schema["Item Types"]["default_value"] = self.common_file_info
        schema["Item Types"]["values"]["items"].update(
            {
                "extensions": {
                    "type": "list",
                    "values": {
                        "type": "str",
                        "description": "A string pattern to match a file extension."
                    },
                    "allows_empty": True,
                    "default_value": [],
                    "description": "A list of file extensions that this item type is interested in."
                },
                "work_path_template": {
                    "type": "template",
                    "description": "",
                    "fields": "context, *",
                    "allows_empty": True,
                },
                "resolution_order": {
                    "type": "int",
                    "default_value": 0,
                    "allows_empty": True,
                    "description": "Resolution order to follow when multiple item types"
                                   "are available the same extension, lower resolution order gets higher priority."
                                   "Item type with a matching work_path_template, gets priority of -1."
                },
                "ignore_sequences": {
                    "type": "bool",
                    "default_value": False,
                    "allows_empty": True,
                    "description": "Setting this to True will force the collected items of this type,"
                                   " to be treated as single frame publishes."
                                   "This is would enable item types to be configured to publish one single file, "
                                   "Even if the collector, collects multiple files."
                }
            }
        )
        schema["Item Types UI"] = {
            "type": "bool",
            "default_value": False,
            "allows_empty": True,
            "description": "Popup UI to allow the user to specify the Item Type if one cannot be determined procedurally."
        }
        return schema

    def process_current_session(self, settings, parent_item):
        """
        Analyzes the current scene open in a DCC and parents a subtree of items
        under the parent_item passed in.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        """
        # default implementation does not do anything
        return []

    def process_file(self, settings, parent_item, path):
        """
        Analyzes the given file and creates one or more items
        to represent it.

        :param dict settings: Configured settings for this collector
        :param parent_item: Root item instance
        :param path: Path to analyze

        :returns: The main item that was created, or None if no item was created
            for the supplied path
        """

        # handle files and folders differently
        if os.path.isdir(path):
            return self._collect_folder(settings, parent_item, path)
        else:
            item = self._collect_file(settings, parent_item, path)
            return [item] if item else []

    def on_context_changed(self, settings, item):
        """
        Callback to update the item on context changes.

        :param dict settings: Configured settings for this collector
        :param item: The Item instance
        """
        # Set the item's work_path_template
        item.properties.work_path_template = self._resolve_work_path_template(settings, item)

        super(FileCollectorPlugin, self).on_context_changed(settings, item)

    ############################################################################
    # protected helper methods

    def _get_work_path_template_from_settings(self, settings, item_type, path):
        """
        Helper method to get the work_path_template from the collector settings object.
        """
        raw_settings = settings["Item Types"].raw_value.get(item_type)
        raw_work_path_template = raw_settings.get("work_path_template") if raw_settings else None

        matched_work_path_template = None

        # If defined, add the work_path_template to the item's properties
        if raw_work_path_template:
            envs = self.parent.sgtk.pipeline_configuration.get_environments()
            template_names_per_env = [
                sgtk.platform.resolve_setting_expression(raw_work_path_template,
                                                         self.parent.engine.instance_name,
                                                         env_name) for
                env_name in envs]

            templates_per_env = [self.parent.get_template_by_name(template_name) for template_name in
                                 template_names_per_env if self.parent.get_template_by_name(template_name)]
            for template in templates_per_env:
                if template.validate(path):
                    # we have a match! update the work_path_template
                    matched_work_path_template = template.name

            if not matched_work_path_template:
                self.logger.warning("Cannot resolve work_path_template. "
                                    "Path doesn't fit any existing templates for %s template." % raw_work_path_template)
                # can't error out since we couldn't find any matching template.
                # raise TankError("The template '%s' does not exist!" % work_path_template)

        # Else see if the path matches an existing template
        elif path:
            # let's try to check if this path fits into any known template
            work_tmpl = self.sgtk.template_from_path(path)
            if not work_tmpl:
                # this path doesn't map to any known templates!
                self.logger.warning("Cannot find a matching template for path: %s" % path)
            else:
                # update the field with correct value so that we can use it everytime for this item
                matched_work_path_template = work_tmpl.name
        else:
            self.logger.warning(
                "Cannot resolve work_path_template. No 'path' or 'work_path_template' setting specified."
            )

        return matched_work_path_template

    def _resolve_work_path_template(self, settings, item):
        """
        Resolve work_path_template from the collector settings for the specified item.

        :param dict settings: Configured settings for this collector
        :param item: The Item instance
        :return: Name of the template.
        """
        path = item.properties.get("path")
        if not path:
            return None

        return self._get_work_path_template_from_settings(settings, item.type, path)

    def _get_item_context_from_path(self, work_path_template, path, parent_item, default_entities=list()):
        """
        Updates the context of the item from the work_path_template/template, if needed.

        :param work_path_template: The work_path template name
        :param item: item to build the context for
        :param parent_item: parent item instance
        :param default_entities: a list of default entities to use during the creation of the
        :class:`sgtk.Context` if not found in the path
        """

        publisher = self.parent

        work_tmpl = publisher.get_template_by_name(work_path_template)

        entities = work_tmpl.get_entities(path)

        existing_types = {entity['type']: entity for entity in entities}
        addable_entities = [entity for entity in default_entities if entity['type'] not in existing_types]

        entities.extend(addable_entities)

        new_context = self.tank.context_from_entities(entities, previous_context=parent_item.context)
        if new_context != parent_item.context:
            return new_context
        else:
            return parent_item.context

    def _collect_file(self, settings, parent_item, path, creation_properties=None):
        """
        Process the supplied file path.

        :param dict settings: Configured settings for this collector
        :param parent_item: parent item instance
        :param path: Path to analyze
        :param creation_properties: The dict of initial properties for the item

        :returns: The item that was created
        """
        publisher = self.parent

        is_sequence = False
        seq_path = publisher.util.get_frame_sequence_path(path)
        seq_files = None
        if seq_path:
            seq_files = publisher.util.get_sequence_path_files(seq_path)
            path = seq_path
            is_sequence = True

        display_name = publisher.util.get_publish_name(path)

        # Make sure file(s) exist on disk
        if is_sequence:
            if not seq_files:
                self.logger.warning(
                    "File sequence does not exist for item: '%s'. Skipping" % display_name,
                    extra={
                        "action_show_more_info": {
                            "label": "Show Info",
                            "tooltip": "Show more info",
                            "text": "Path does not exist: %s" % (path,)
                        }
                    }
                )
                return
        else:
            if not os.path.exists(path):
                self.logger.warning(
                    "File does not exist for item: '%s'. Skipping" % display_name,
                    extra={
                        "action_show_more_info": {
                            "label": "Show Info",
                            "tooltip": "Show more info",
                            "text": "Path does not exist: %s" % (path,)
                        }
                    }
                )
                return

        file_item = self._add_file_item(settings, parent_item, path, is_sequence, seq_files,
                                        creation_properties=creation_properties)
        if file_item:
            if is_sequence:
                # include an indicator that this is an image sequence and the known
                # file that belongs to this sequence
                file_info = (
                    "The following files were collected:<br>"
                    "<pre>%s</pre>" % (pprint.pformat(seq_files),)
                )
            else:
                file_info = (
                    "The following file was collected:<br>"
                    "<pre>%s</pre>" % (path,)
                )

            self.logger.info(
                "Collected item: %s" % file_item.name,
                extra={
                    "action_show_more_info": {
                        "label": "Show File(s)",
                        "tooltip": "Show the collected file(s)",
                        "text": file_info
                    }
                }
            )

        return file_item

    def _collect_folder(self, settings, parent_item, folder, creation_properties=None):
        """
        Process the supplied folder path.

        :param dict settings: Configured settings for this collector
        :param parent_item: parent item instance
        :param folder: Path to analyze
        :param creation_properties: The dict of initial properties for the item

        :returns: The item that was created
        """

        # make sure the path is normalized. no trailing separator, separators
        # are appropriate for the current os, no double separators, etc.
        folder = sgtk.util.ShotgunPath.normalize(folder)

        publisher = self.parent
        known_seq_extensions = _build_seq_extensions_list(settings)
        frame_sequences = publisher.util.get_frame_sequences(folder, known_seq_extensions)

        file_items = []
        for path, seq_files in frame_sequences:
            file_item = self._add_file_item(settings, parent_item, path, True, seq_files,
                                            creation_properties=creation_properties)
            if file_item:
                # include an indicator that this is an image sequence and the known
                # file that belongs to this sequence
                file_info = (
                    "The following files were collected:<br>"
                    "<pre>%s</pre>" % (pprint.pformat(seq_files),)
                )

                self.logger.info(
                    "Collected item: %s" % file_item.name,
                    extra={
                        "action_show_more_info": {
                            "label": "Show File(s)",
                            "tooltip": "Show the collected file(s)",
                            "text": file_info
                        }
                    }
                )
                file_items.append(file_item)

        if not file_items:
            self.logger.warning("No file sequences found in: %s" % (folder,))

        return file_items

    def _add_file_item(self, settings, parent_item, path, is_sequence=False, seq_files=None, item_name=None,
                       item_type=None, context=None, creation_properties=None):
        """
        Creates a file item

        :param dict settings: Configured settings for this collector
        :param parent_item: parent item instance
        :param path: Path to analyze
        :param is_sequence: Bool as to whether to treat the path as a part of a sequence
        :param seq_files: A list of files in the sequence
        :param item_name: The name of the item instance
        :param item_type: The type of the item instance
        :param context: The :class:`sgtk.Context` to set for the item
        :param creation_properties: The dict of initial properties for the item

        :returns: The item that was created
        """
        publisher = self.parent

        # Get the item name from the path
        if not item_name:
            item_name = publisher.util.get_publish_name(path)

        # Define the item's properties
        properties = creation_properties or {}

        # set the path and is_sequence properties for the plugins to use
        properties["path"] = path
        properties["is_sequence"] = is_sequence

        # Lookup this item's item_type from the settings object
        if not item_type:
            # use the properties dict here, in case user doesn't use the creation_properties arg
            item_type = self._get_item_type_from_settings(settings, path, is_sequence,
                                                          creation_properties=properties)

        type_info = self._get_item_type_info(settings, item_type)
        ignore_sequence = type_info["ignore_sequences"]

        # item intentionally ignores sequences
        if ignore_sequence:
            properties["is_sequence"] = False
        # If a sequence, add the sequence path
        if is_sequence:
            properties["sequence_paths"] = seq_files

        if not context:
            # See if we can get a resolved work_path_template from the settings object
            work_path_template = self._get_work_path_template_from_settings(settings, item_type, path)
            if work_path_template:
                # If defined, attempt to use it and the input path to get the item's initial context
                context = self._get_item_context_from_path(work_path_template, path, parent_item)

            # Otherwise, just set the context to the parent's context
            else:
                context = parent_item.context

        # create and populate the item
        file_item = self._add_item(settings,
                                   parent_item,
                                   item_name,
                                   item_type,
                                   context,
                                   properties)

        # if the supplied path is an image, use the path as the thumbnail.
        image_type = item_type.split(".")[1]
        if image_type in KNOWN_IMAGE_TYPES:
            if is_sequence:
                file_item.set_thumbnail_from_path(seq_files[0])
            else:
                file_item.set_thumbnail_from_path(path)

            # disable thumbnail creation since we get it for free
            file_item.thumbnail_enabled = False

        return file_item

    def _get_filtered_item_types_from_settings(self, settings, path, is_sequence, creation_properties):

        """
        Returns a list of tuples containing (resolution_order, work_path_template, item_type).
        This filtered list of item types can then be passed down to resolve the correct item_type.

        :param dict settings: Configured settings for this collector
        :param path: The file path to identify type info for
        :param is_sequence: Bool whether or not path is a sequence path
        :param creation_properties: The dict of initial properties for the item
        """
        publisher = self.parent

        # extract the components of the supplied path
        file_info = publisher.util.get_file_path_components(path)
        extension = file_info["extension"]
        filename = file_info["filename"]

        # tuple of resolution_order, work_path_template and item_type
        template_item_type_mapping = list()

        # look for the extension in the common file type info dict
        # using the raw value to get a raw work_path_template
        for current_item_type, type_info in settings["Item Types"].value.iteritems():
            if any(fnmatch.fnmatch(current_extension, extension) for current_extension in type_info["extensions"]):
                # matched work path template
                matched_work_path_template = None
                # resolution order to follow in case matched_work_path_template is None.
                matched_resolution_order = type_info["resolution_order"]
                # match this raw template against all environments, to find a matching template
                if type_info["work_path_template"]:
                    envs = self.parent.sgtk.pipeline_configuration.get_environments()
                    template_names_per_env = [
                        sgtk.platform.resolve_setting_expression(
                            settings["Item Types"].raw_value[current_item_type]["work_path_template"],
                            self.parent.engine.instance_name,
                            env_name) for env_name in envs
                    ]

                    templates_per_env = [self.parent.get_template_by_name(template_name) for template_name in
                                         template_names_per_env if self.parent.get_template_by_name(template_name)]
                    for template in templates_per_env:
                        if template.validate(path):
                            # we have a match! update the work_path_template
                            matched_work_path_template = template.name

                ignore_sequences = type_info["ignore_sequences"]
                # If we are dealing with a sequence, first check if we have a
                # separate definition for a sequence of this type specifically,
                # and if so, use that instead.
                # If an item intentionally ignores sequences, simply add the item_type without turning it to
                # an item_type that resolves files as sequences.
                if not ignore_sequences and is_sequence and not current_item_type.endswith(".sequence"):
                    tmp_type = "%s.%s" % (current_item_type, "sequence")
                    if tmp_type in settings["Item Types"].value:
                        template_item_type_mapping.append((matched_resolution_order, matched_work_path_template,
                                                           tmp_type))
                        continue

                template_item_type_mapping.append((matched_resolution_order, matched_work_path_template,
                                                   current_item_type))

                max_resolution_order = max(
                    [resolution_order for resolution_order, work_path_template, item_type in template_item_type_mapping]
                )

                # sort the list on resolution_order, giving preference to a matching template
                template_item_type_mapping.sort(
                    key=lambda elem: elem[0] if not elem[1] else elem[0]-max_resolution_order)

        return template_item_type_mapping

    def _get_item_type_from_settings(self, settings, path, is_sequence, creation_properties):
        """
        Return the item type for the given filename from the settings object.

        The method will try to identify the file as a common file type. If not,
        it will use the mimetype category. If the file still cannot be
        identified, it will fallback to a generic file type.

        :param dict settings: Configured settings for this collector
        :param path: The file path to identify type info for
        :param is_sequence: Bool whether or not path is a sequence path
        :param creation_properties: The dict of initial properties for the item

        :return: A string representing the item_type::

        The item type will be of the form `file.<type>` where type is a specific
        common type or a generic classification of the file.
        """
        publisher = self.parent

        # extract the components of the supplied path
        file_info = publisher.util.get_file_path_components(path)
        extension = file_info["extension"]
        filename = file_info["filename"]

        # default values used if no specific type can be determined
        item_type = "file.unknown"

        # keep track if a common type was identified for the extension
        common_type_found = False

        # tuple of resolution_order, work_path_template and item_type
        template_item_type_mapping = self._get_filtered_item_types_from_settings(settings, path,
                                                                                 is_sequence, creation_properties)

        # this should work fine in case there is no work path template defined too
        # this method gives preference to the first match that we get for any template
        # also, there should never be a match with more than one templates, since template_from_path will fail too.
        if len(template_item_type_mapping):
            # found the extension in the item types lookup.
            common_type_found = True

            resolution_order, work_path_template, item_type = template_item_type_mapping[0]
            # 0 index contains a matching work_path_template if any.
            # if there is no match that means we need to ask the user
            if not work_path_template and len(template_item_type_mapping) > 1:
                # if items_type are more than 1 then only pop-up UI and if the setting has enabled UI
                if settings.get("Item Types UI") and settings.get("Item Types UI").value:
                    ui_object = PopupItemTypesListUI(self.parent.engine, path,
                                                     [mapping[2] for mapping in template_item_type_mapping])
                    item_type = ui_object.selected_item

        if not common_type_found:
            # no common type match. try to use the mimetype category. this will
            # be a value like "image/jpeg" or "video/mp4". we'll extract the
            # portion before the "/" and use that for display.
            (category_type, _) = mimetypes.guess_type(filename)

            if category_type:

                # mimetypes.guess_type can return unicode strings depending on
                # the system's default encoding. If a unicode string is
                # returned, we simply ensure it's utf-8 encoded to avoid issues
                # with toolkit, which expects utf-8
                if isinstance(category_type, unicode):
                    category_type = category_type.encode("utf-8")

                # the category portion of the mimetype
                category = category_type.split("/")[0]

                item_type = "file.%s" % (category,)

        type_info = self._get_item_type_info(settings, item_type)
        ignore_sequences = type_info["ignore_sequences"]
        # if the supplied image path is part of a sequence. alter the
        # type info to account for this.
        # If an item intentionally ignores sequences, simply add the item_type without turning it to
        # an item_type that resolves files as sequences.
        if not ignore_sequences and is_sequence and not item_type.endswith(".sequence"):
            item_type = "%s.%s" % (item_type, "sequence")

        return str(item_type)

    def _get_item_type_info(self, settings, item_type):
        """
        Return the dictionary corresponding to this item's 'Item Types' settings.

        :param dict settings: Configured settings for this collector
        :param item_type: The type of Item to identify info for

        :return: A dictionary of information about the item to create::

            # item_type = "file.image.sequence"

            {
                "extensions": ["jpeg", "jpg", "png"],
                "type_display": "Rendered Image Sequence",
                "icon_path": "/path/to/some/icons/folder/image_sequence.png",
                "work_path_template": "some_template_name"
            }
        """
        publisher = self.parent

        item_info = super(FileCollectorPlugin, self)._get_item_type_info(settings, item_type)

        # define default values for the schema
        item_info.setdefault("resolution_order", 0)
        item_info.setdefault("ignore_sequences", False)

        # If this is a file item...
        if item_type.startswith("file."):

            # This can happen if we did not match a common file type but did match a mimetype...
            if "extensions" not in item_info:
                file_type = item_type.split(".")[1]

                # set the type_display to the mimetype
                item_info["type_display"] = "%s File" % file_type.title()

                # set the icon path if the file exists
                icon_path = "{self}/hooks/icons/%s.png" % file_type
                if os.path.exists(publisher.expand_path(icon_path)):
                    item_info["icon_path"] = icon_path

        # If the specified item type is a sequence, alter the type_display to account for this.
        if item_type.endswith(".sequence") and \
           not item_info["type_display"].endswith("Sequence"):
            item_info["type_display"] += " Sequence"
            item_info["icon_path"] = "{self}/hooks/icons/image_sequence.png"

        # everything should now be populated, so return the dictionary
        return item_info

    def _get_template_fields_from_path(self, item, template_name, path):
        """
        Get the fields by parsing the input path using the template derived from
        the input template name.
        """
        publisher = self.parent

        tmpl_obj = publisher.get_template_by_name(template_name)
        if not tmpl_obj:
            # this template was not found in the template config!
            raise TankError("The template '%s' does not exist!" % template_name)

        tmpl_fields = tmpl_obj.validate_and_get_fields(path)
        if tmpl_fields:
            self.logger.info(
                "Parsed path using template '%s' for item: %s" % (tmpl_obj.name, item.name),
                extra={
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show more info",
                        "text": "Path parsed by template '%s': %s\nResulting fields:\n%s" %
                        (template_name, path, pprint.pformat(tmpl_fields))
                    }
                }
            )
            return tmpl_fields

        self.logger.warning(
            "Path does not match template for item: %s" % (item.name),
            extra={
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": "Path cannot be parsed by template '%s': %s" %
                    (template_name, path)
                }
            }
        )
        return {}

    def _resolve_item_fields(self, settings, item):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        publisher = self.parent

        fields = super(FileCollectorPlugin, self)._resolve_item_fields(settings, item)

        # Extra processing for items with files
        path = item.properties.get("path")
        if path:

            file_info = publisher.util.get_file_path_components(path)

            # If its a sequence, use the first resolved path in the sequence instead
            if item.properties.get("is_sequence", False):
                path = item.properties.sequence_paths[0]

            # If there is a valid work_path_template, attempt to get any fields from it
            work_path_template = item.properties.get("work_path_template")
            if work_path_template:
                tmpl_fields = self._get_template_fields_from_path(item, work_path_template, path)
            else:
                tmpl_fields = {}

            # If version wasn't parsed by the template, try parsing the path manually
            if "version" not in tmpl_fields:
                version = publisher.util.get_version_number(path)
                if version:
                    tmpl_fields["version"] = version

            # Update the fields dict with the template fields
            fields.update(tmpl_fields)

            # If not already populated, attempt to get the width and height from the image
            # use extensions instead of item types
            known_seq_extensions = _build_seq_extensions_list(settings)
            if file_info["extension"] in known_seq_extensions:
                if "width" not in fields or "height" not in fields:
                    # If image, use OIIO to introspect file and get WxH
                    try:
                        from OpenImageIO import ImageInput
                        fh = ImageInput.open(str(path))
                        if fh:
                            try:
                                spec = fh.spec()
                                fields["width"] = spec.width
                                fields["height"] = spec.height
                            except Exception as e:
                                self.logger.error(
                                    "Error getting resolution for item: %s" % (item.name,),
                                    extra={
                                        "action_show_more_info": {
                                            "label": "Show Info",
                                            "tooltip": "Show more info",
                                            "text": "Error reading file: %s\n  ==> %s" % (path, str(e))
                                        }
                                    }
                                )
                            finally:
                                fh.close()
                    except Exception as e:
                        self.logger.warning(str(e) + ". Cannot determine width/height from %s." % path)

            # Get the file extension if not already defined
            if "extension" not in fields:
                fields["extension"] = file_info["extension"]

            # Force use of %d format
            if item.properties.get("is_sequence", False):
                fields["SEQ"] = "FORMAT: %d"
            else:
                # make sure we update the SEQ key in case of non-sequence to None
                fields["SEQ"] = None

        return fields


def _build_seq_extensions_list(settings):

    file_types = ["file.%s" % x for x in KNOWN_IMAGE_TYPES]
    extensions = set()
    defined_file_types = settings['Item Types'].keys()
    # get defined_file_type based on file_types
    for file_type in file_types:
        for defined_file_type in defined_file_types:
            if defined_file_type.startswith(file_type):
                extensions.update(settings['Item Types'][defined_file_type]["extensions"].value)
                extensions.update(e_item.upper() for e_item in settings['Item Types'][defined_file_type]["extensions"].value)
                break
    # get all the image mime type extensions as well
    mimetypes.init()
    types_map = mimetypes.types_map
    for (ext, mimetype) in types_map.iteritems():
        if mimetype.startswith("image/"):
            extensions.add(ext.lstrip("."))
            extensions.add(ext.lstrip(".").upper())

    return list(extensions)


KNOWN_IMAGE_TYPES = ("render", "texture", "image", "deep_render")
