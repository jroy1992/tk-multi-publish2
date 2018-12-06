# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import mimetypes
import os
import datetime
import glob
import pprint
import urllib
import sgtk
from sgtk import TankError

HookBaseClass = sgtk.get_hook_baseclass()


# This is a dictionary of file type info that allows the basic collector to
# identify common production file types and associate them with a display name,
# item type, and config icon.
DEFAULT_ITEM_TYPES = {
    "file.alembic": {
        "extensions": ["abc"],
        "icon": "{self}/hooks/icons/alembic.png",
        "type_display": "Alembic Cache"
    },
    "file.3dsmax": {
        "extensions": ["max"],
        "icon": "{self}/hooks/icons/3dsmax.png",
        "type_display": "3dsmax Scene"
    },
    "file.nukestudio": {
        "extensions": ["hrox"],
        "icon": "{self}/hooks/icons/nukestudio.png",
        "type_display": "NukeStudio Project"
    },
    "file.houdini": {
        "extensions": ["hip", "hipnc"],
        "icon": "{self}/hooks/icons/houdini.png",
        "type_display": "Houdini Scene"
    },
    "file.maya": {
        "extensions": ["ma", "mb"],
        "icon": "{self}/hooks/icons/maya.png",
        "type_display": "Maya Scene"
    },
    "file.motionbuilder": {
        "extensions": ["fbx"],
        "icon": "{self}/hooks/icons/motionbuilder.png",
        "type_display": "Motion Builder FBX",
    },
    "file.nuke": {
        "extensions": ["nk"],
        "icon": "{self}/hooks/icons/nuke.png",
        "type_display": "Nuke Script"
    },
    "file.photoshop": {
        "extensions": ["psd", "psb"],
        "icon": "{self}/hooks/icons/photoshop.png",
        "type_display": "Photoshop Image"
    },
    "file.render": {
        "extensions": ["dpx", "exr"],
        "icon": "{self}/hooks/icons/image.png",
        "type_display": "Rendered Image"
    },
    "file.texture": {
        "extensions": ["tif", "tiff", "tx", "tga", "dds", "rat"],
        "icon": "{self}/hooks/icons/texture.png",
        "type_display": "Texture Image"
    },
    "file.image": {
        "extensions": ["jpeg", "jpg", "png"],
        "icon": "{self}/hooks/icons/image.png",
        "type_display": "Image"
    },
    "file.video": {
        "extensions": ["mov", "mp4"],
        "icon": "{self}/hooks/icons/video.png",
        "type_display": "Movie"
    }
}


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
                    "icon": <icon path>,
                    "item_type": <item type>
                },
                <Publish Type>: {
                    "extensions": [<ext>, <ext>, ...],
                    "icon": <icon path>,
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
        schema["Item Types"]["values"]["items"] = {
            "extensions": {
                "type": "list",
                "values": {
                    "type": "str",
                    "description": "A string pattern to match a file extension."
                },
                "description": "A list of file extensions that this item type is interested in."
            },
            "icon": {
                "type": "config_path",
                "description": ""
            },
            "type_display": {
                "type": "str",
                "description": ""
            },
            "work_path_template": {
                "type": "template",
                "description": "",
                "fields": ["context", "*"],
                "allows_empty": True,
            },
        }
        schema["Item Types"]["description"] = (
            "Dictionary of file type info that allows the basic "
            "collector to identify common production file types and "
            "associate them with a display name, item type, and config "
            "icon."
        )
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

        path = item.properties.path
        is_sequence = item.properties.is_sequence

        item_info = self._get_item_info(settings, path, is_sequence)

        item.properties.work_path_template = self._resolve_work_path_template(item_info, path)

        # Set the item's fields property
        item.properties.fields = self._resolve_item_fields(item)


    def _resolve_work_path_template(self, properties, path):
        """
        Resolve work_path_template from the properties.
        The signature uses properties, so that it can resolve the template even if the item object hasn't been created.

        :param properties: properties that have/will be used to build item object.
        :param path: path to be used to get the templates, using template_from_path.
        :return: Name of the template.
        """

        work_path_template = properties.get("work_path_template")

        # If defined, add the work_path_template to the item's properties
        if work_path_template:
            work_tmpl = self.parent.get_template_by_name(work_path_template)
            if not work_tmpl:
                # this template was not found in the template config!
                raise TankError("The template '%s' does not exist!" % work_path_template)

        # Else see if the path matches an existing template
        else:
            # let's try to check if this path fits into any known template
            work_tmpl = self.sgtk.template_from_path(path)
            if not work_tmpl:
                # this path doesn't map to any known templates!
                self.logger.warning("Cannot find a matching template for path: %s" % path)
            else:
                # update the field with correct value so that we can use it everytime for this item
                work_path_template = work_tmpl.name

        return work_path_template


    def _get_item_context_from_path(self, parent_item, properties, path, default_entities=list()):
        """Updates the context of the item from the work_path_template/template, if needed.

        :param properties: properties of the item.
        :param path: path to build the context from.
        :param default_entities: a list of default entities to use during the creation of the
        :class:`sgtk.Context` if not found in the path
        """

        publisher = self.parent

        work_path_template = self._resolve_work_path_template(properties, path)

        if work_path_template:
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


    def _collect_file(self, settings, parent_item, path):
        """
        Process the supplied file path.

        :param dict settings: Configured settings for this collector
        :param parent_item: parent item instance
        :param path: Path to analyze
        :param frame_sequence: Treat the path as a part of a sequence

        :returns: The item that was created
        """
        publisher = self.parent

        # make sure the path is normalized. no trailing separator, separators
        # are appropriate for the current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(path)

        # Check to see if the input path contains a frame_spec
        frame_path = publisher.util.get_path_for_frame(path, 1001)
        if frame_path:
            # If so, set the seq_path equal to input path
            seq_path = path
        else:
            # Else check if the input path contains a frame number
            seq_path = publisher.util.get_frame_sequence_path(path)

        seq_files = []
        is_sequence = False
        if seq_path:

            # find files that match the pattern
            seq_pattern = publisher.util.get_path_for_frame(seq_path, "*")
            seq_files = [f for f in glob.iglob(seq_pattern) if os.path.isfile(f)]

            # Sort the resulting list
            seq_files.sort()

            # Set path to seq_path
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

        return self._add_file_item(settings, parent_item, path, is_sequence, seq_files)


    def _collect_folder(self, settings, parent_item, folder):
        """
        Process the supplied folder path.

        :param dict settings: Configured settings for this collector
        :param parent_item: parent item instance
        :param folder: Path to analyze

        :returns: The item that was created
        """

        # make sure the path is normalized. no trailing separator, separators
        # are appropriate for the current os, no double separators, etc.
        folder = sgtk.util.ShotgunPath.normalize(folder)

        publisher = self.parent
        frame_sequences = publisher.util.get_frame_sequences(folder, SEQ_EXTENSIONS_LIST)

        file_items = []
        for path, seq_files in frame_sequences:
            file_items += filter(None, [self._add_file_item(settings, parent_item, path, True, seq_files)])

        if not file_items:
            self.logger.warning("No file sequences found in: %s" % (folder,))

        return file_items


    def _add_file_item(self, settings, parent_item, path, is_sequence=False, seq_files=None):
        """
        Creates a file item

        :param dict settings: Configured settings for this collector
        :param parent_item: parent item instance
        :param path: Path to analyze
        :param is_sequence: Bool as to whether to treat the path as a part of a sequence
        :param seq_files: A list of files in the sequence

        :returns: The item that was created
        """
        publisher = self.parent

        # get info for the extension
        item_info = self._get_item_info(settings, path, is_sequence)

        icon_path = item_info["icon_path"]
        item_type = item_info["item_type"]
        type_display = item_info["type_display"]
        work_path_template = item_info["work_path_template"]

        display_name = publisher.util.get_publish_name(path)

        # Define the item's properties
        properties = {}

        # set the path and is_sequence properties for the plugins to use
        properties["path"] = path
        properties["is_sequence"] = is_sequence

        # If a sequence, add the sequence path
        if is_sequence:
            properties["sequence_paths"] = seq_files

        if work_path_template:
            properties["work_path_template"] = work_path_template

        # build the context of the item
        context = self._get_item_context_from_path(parent_item, properties, path)

        # create and populate the item
        file_item = parent_item.create_item(
            item_type,
            type_display,
            display_name,
            collector=self.plugin,
            context=context,
            properties=properties
        )

        # Set the icon path
        file_item.set_icon_from_path(icon_path)

        # if the supplied path is an image, use the path as the thumbnail.
        if (item_type.startswith("file.image") or
            item_type.startswith("file.texture") or
            item_type.startswith("file.render")):

            if is_sequence:
                file_item.set_thumbnail_from_path(seq_files[0])
            else:
                file_item.set_thumbnail_from_path(path)

            # disable thumbnail creation since we get it for free
            file_item.thumbnail_enabled = False

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
            "Collected item: %s" % display_name,
            extra={
                "action_show_more_info": {
                    "label": "Show File(s)",
                    "tooltip": "Show the collected file(s)",
                    "text": file_info
                }
            }
        )

        return file_item


    def _get_item_info(self, settings, path, is_sequence):
        """
        Return a tuple of display name, item type, and icon path for the given
        filename.

        The method will try to identify the file as a common file type. If not,
        it will use the mimetype category. If the file still cannot be
        identified, it will fallback to a generic file type.

        :param dict settings: Configured settings for this collector
        :param path: The file path to identify type info for

        :return: A dictionary of information about the item to create::

            # path = "/path/to/some/file.0001.exr"

            {
                "item_type": "file.image.sequence",
                "type_display": "Rendered Image Sequence",
                "icon_path": "/path/to/some/icons/folder/image_sequence.png",
            }

        The item type will be of the form `file.<type>` where type is a specific
        common type or a generic classification of the file.
        """
        publisher = self.parent

        # extract the components of the supplied path
        file_info = publisher.util.get_file_path_components(path)
        extension = file_info["extension"]
        filename = file_info["filename"]

        # default values used if no specific type can be determined
        type_display = "File"
        item_type = "file.unknown"
        work_path_template = None
        default_icon = "{self}/hooks/icons/file.png"

        # keep track if a common type was identified for the extension
        common_type_found = False

        # look for the extension in the common file type info dict
        for item_type, type_info in settings["Item Types"].value.iteritems():

            if extension in type_info["extensions"]:
                # found the extension in the common types lookup. extract the
                # type_display, icon path, and optional work_path_template.
                type_display = type_info["type_display"]
                icon_path = type_info["icon"]
                work_path_template = type_info.get("work_path_template")
                common_type_found = True

                # If we are dealing with a sequence, first check if we have a
                # separate definition for a sequence of this type specifically,
                # and if so, use that instead.
                if is_sequence and not item_type.endswith(".sequence"):
                    tmp_type = "%s.%s" % (item_type, "sequence")
                    if tmp_type in settings["Item Types"].value:
                        continue

                # Otherwise, we've found our match
                break

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

                type_display = "%s File" % (category.title(),)
                item_type = "file.%s" % (category,)
                icon_path = "{self}/hooks/icons/%s.png" % (category,)

        # construct a full path to the icon given the name defined above
        icon_path = publisher.expand_path(icon_path)
        if not os.path.exists(icon_path):
            icon_path = publisher.expand_path(default_icon)

        if is_sequence:
            # if the supplied image path is part of a sequence. alter the
            # type info to account for this.
            type_display = "%s Sequence" % (type_display,)
            if not item_type.endswith(".sequence"):
                item_type = "%s.%s" % (item_type, "sequence")
            icon_path = "{self}/hooks/icons/image_sequence.png"

        # everything should be populated. return the dictionary
        return dict(
            icon_path=icon_path,
            item_type=item_type,
            type_display=type_display,
            work_path_template=work_path_template
        )


    def _get_version_number_r(self, item):
        """
        Recurse up item hierarchy to determine version number
        """
        publisher = self.parent
        path = item.properties.get("path")

        if not path:
            if not item.is_root:
                version = self._get_version_number_r(item.parent)
            else:
                version = 1
        else:
            version = publisher.util.get_version_number(path)
            if not version:
                if not item.is_root:
                    version = self._get_version_number_r(item.parent)
                else:
                    version = 1
        return version


    def _get_name_field_r(self, item):
        """
        Recurse up item hierarchy to determine the name field
        """
        if not item:
            return None

        if "fields" in item.properties:
            name_field = item.properties.fields.get("name")
            if name_field:
                return name_field

        if item.parent:
            return self._get_name_field_r(item.parent)

        return None


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


    def _resolve_item_fields(self, item):
        """
        Helper method used to get fields that might not normally be defined in the context.
        Intended to be overridden by DCC-specific subclasses.
        """
        publisher = self.parent
        if item.properties.is_sequence:
            path = item.properties.sequence_paths[0]
        else:
            path = item.properties.path

        fields = {}

        # If there is a valid work_path_template, attempt to get any fields from it
        work_path_template = item.properties.get("work_path_template")
        if work_path_template:
            fields.update(self._get_template_fields_from_path(item, work_path_template, path))

        # If not already populated, attempt to get the width and height from the image
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
            except ImportError as e:
                self.logger.error(str(e))

        # If item has version in file name, use it, otherwise, recurse up item hierarchy
        # Note: this intentionally overwrites any value found in the work file
        fields["version"] = self._get_version_number_r(item)

        # Get the file extension if not already defined
        if "extension" not in fields:
            file_info = publisher.util.get_file_path_components(path)
            fields["extension"] = file_info["extension"]

        # Force use of %d format
        if item.properties.is_sequence:
            fields["SEQ"] = "FORMAT: %d"

        # use %V - full view printout as default for the eye field
        fields["eye"] = "%V"

        # add in date values for YYYY, MM, DD
        today = datetime.date.today()
        fields["YYYY"] = today.year
        fields["MM"] = today.month
        fields["DD"] = today.day

        # Try to set the name field if not defined
        if "name" not in fields:
            # First attempt to get it from the parent item
            name_field = self._get_name_field_r(item.parent)
            if name_field:
                fields["name"] = name_field

            # Else attempt to use a sanitized task name
            elif item.context.task:
                name_field = item.context.task["name"]
                fields["name"] = urllib.quote(name_field.replace(" ", "_").lower(), safe='')

        return fields


def _build_seq_extensions_list():

    file_types = ["file.photoshop", "file.render", "file.texture", "file.image"]
    extensions = set()

    for file_type in file_types:
        extensions.update(DEFAULT_ITEM_TYPES[file_type]["extensions"])

    # get all the image mime type extensions as well
    mimetypes.init()
    types_map = mimetypes.types_map
    for (ext, mimetype) in types_map.iteritems():
        if mimetype.startswith("image/"):
            extensions.add(ext.lstrip("."))

    return list(extensions)

SEQ_EXTENSIONS_LIST = _build_seq_extensions_list()
