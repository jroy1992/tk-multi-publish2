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
import copy
import stat
import traceback
import pprint
import sgtk
from sgtk.util.filesystem import copy_file, ensure_folder_exists, safe_delete_file, symlink_file

from .base import PluginBase

class PublishPlugin(PluginBase):
    """
    This class defines the required interface for a publish plugin. Publish
    plugins are responsible for operating on items collected by the collector
    plugin. Publish plugins define which items they will operate on as well as
    the execution logic for each phase of the publish process.
    """

    ############################################################################
    # Plugin properties

    @property
    def id(self):
        """
        Unique string identifying this plugin.
        """
        return self._id

    @id.setter
    def id(self, new_id):
        """
        Allows to set the unique string identifying this plugin.
        """
        self._id = new_id

    @property
    def icon(self):
        """
        The path to an icon on disk that is representative of this plugin
        (:class:`str`).

        The icon will be displayed on the left side of the task driven by this
        plugin, as shown in the image below.

        .. image:: ./resources/task_icon.png

        |

        Icons can be stored within the same bundle as the plugin itself and
        referenced relative to the disk location of the plugin, accessible via
        :meth:`sgtk.Hook.disk_location`.

        Example implementation:

        .. code-block:: python

            @property
            def icon(self):

                return os.path.join(
                    self.disk_location,
                    "icons",
                    "publish.png"
                )

        .. note:: Publish plugins drive the tasks that operate on publish items.
            It can be helpful to think of items as "things" and tasks as the
            "actions" that operate on those "things". A publish icon that
            represents some type of action can help artists understand the
            distinction between items and tasks in the interface.

        """
        return None

    @property
    def name(self):
        """
        The general name for this plugin (:class:`str`).

        This value is not generally used for display. Instances of the plugin
        are defined within the app's configuration and those instance names are
        what is shown in the interface for the tasks.
        """
        raise NotImplementedError

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does (:class:`str`).

        The string can contain html for formatting for display in the UI (any
        html tags supported by Qt's rich text engine).

        The description is displayed via the plugin's default
        :meth:`create_settings_widget` implementation, as shown in the image
        below:

        .. image:: ./resources/plugin_description.png

        |

        A simple implementation example:

        .. code-block:: python

            @property
            def description(self):

                return '''
                Creates a publish in Shotgun.

                A <b>Publish</b> entry will be created in Shotgun which will
                include a reference to the file's path on disk. Other users will
                be able to access the published file via the
                <b><a href='%s'>Loader</a></b> so long as they have access to
                the file's location on disk.
                ''' % (loader_url,)

        """
        raise NotImplementedError

    @property
    def settings_schema(self):
        """
        A :class:`dict` defining the configuration interface for this plugin.

        The dictionary can include any number of settings required by the
        plugin, and takes the form::

            {
                <setting_name>: {
                    "type": <type>,
                    "default": <default>,
                    "description": <description>
                },
                <setting_name>: {
                    "type": <type>,
                    "default": <default>,
                    "description": <description>
                },
                ...
            }

        The keys in the dictionary represent the names of the settings. The
        values are a dictionary comprised of 3 additional key/value pairs.

        * ``type``: The type of the setting. This should correspond to one of
          the data types that toolkit accepts for app and engine settings such
          as ``hook``, ``template``, ``string``, etc.
        * ``default``: The default value for the settings. This can be ``None``.
        * ``description``: A description of the setting as a string.

        Example implementation:

        .. code-block:: python

            @property
            def settings(self):
                return {
                    "Publish Template": {
                        "type": "template",
                        "default": None,
                        "description": "The output path template for this plugin."
                    },
                    "Resolution": {
                        "type": "str",
                        "default": "1920x1080"
                        "description": "The output resolution to export before publishing."
                    }
                }

        The settings are exposed via the ``settings`` key as the plugins are
        configured via the ``publish_plugins`` setting in the app's
        configuration. Example::

            publish_plugins:
                - name: Export and Publish
                  hook: "{config}/export_and_publish.py"
                  settings:
                      Publish Template: export_template
                      Resolution: 2048x1556

        The values configured for the plugin will be supplied via settings
        parameter in the :meth:`accept`, :meth:`validate`, :meth:`publish`, and
        :meth:`finalize` methods.

        The values also drive the custom UI defined by the plugin whick allows
        artists to manipulate the settings at runtime. See the
        :meth:`create_settings_widget`, :meth:`set_ui_settings`, and
        :meth:`get_ui_settings` for additional information.

        .. note:: See the hooks defined in the publisher app's ``hooks/`` folder
           for additional example implementations.
        """
        return {
            "Item Type Filters": {
                "type": "list",
                "values": {
                    "type": "str",
                    "description": "A string pattern to match an item type against."
                },
                "default_value": [],
                "description": "A list of item types that this plugin is interested in."
            },
            "Item Type Settings": {
                "type": "dict",
                "values": {
                    "type": "dict"
                },
                "default_value": {},
                "description": (
                    "A dict of plugin settings keyed by item type. Each entry in the dict "
                    "is itself a dict in which each item is the plugin attribute name and value."
                ),
            }
        }

    @property
    def item_filters(self):
        """
        A :class:`list` of item type wildcard :class:`str` objects that this
        plugin is interested in.

        As items are collected by the collector hook, they are given an item
        type string (see :meth:`~.api.PublishItem.create_item`). The strings
        provided by this property will be compared to each collected item's
        type.

        Only items with types matching entries in this list will be considered
        by the :meth:`accept` method. As such, this method makes it possible to
        quickly identify which items the plugin may be interested in. Any
        sophisticated acceptance logic is deferred to the :meth:`accept` method.

        Strings can contain glob patters such as ``*``, for example ``["maya.*",
        "file.maya"]``.
        """
        return self.plugin.settings["Item Type Filters"].value

    ############################################################################
    # Publish processing methods

    def init_task_settings(self, item):
        """
        Method called by the publisher to determine the initial settings for the
        instantiated task.

        :param item: The parent item of the task
        :returns: dictionary of settings for this item's task
        """
        # Return the item-type specific settings
        if item.type not in self.plugin.settings["Item Type Settings"]:
            msg = "Key: %s\n%s" % (item.type, pprint.pformat(self.plugin.settings["Item Type Settings"]))
            self.logger.warning(
                "'Item Type Settings' are missing for item type: '%s'" % item.type,
                extra={
                    "action_show_more_info": {
                        "label": "Show Info",
                        "tooltip": "Show more info",
                        "text": msg
                    }
                }
            )
            return {}
        return self.plugin.settings["Item Type Settings"].get(item.type)

    def accept(self, task_settings, item):
        """
        This method is called by the publisher to see if the plugin accepts the
        supplied item for processing.

        Only items matching the filters defined via the :data:`item_filters`
        property will be presented to this method.

        A publish task will be generated for each item accepted here.

        This method returns a :class:`dict` of the following form::

            {
                "accepted": <bool>,
                "enabled": <bool>,
                "visible": <bool>,
                "checked": <bool>,
            }

        The keys correspond to the acceptance state of the supplied item. Not
        all keys are required. The keys are defined as follows:

        * ``accepted``: Indicates if the plugin is interested in this value at all.
          If ``False``, no task will be created for this plugin. Required.
        * ``enabled``: If ``True``, the created task will be enabled in the UI,
          otherwise it will be disabled (no interaction allowed). Optional,
          ``True`` by default.
        * ``visible``: If ``True``, the created task will be visible in the UI,
          otherwise it will be hidden. Optional, ``True`` by default.
        * ``checked``: If ``True``, the created task will be checked in the UI,
          otherwise it will be unchecked. Optional, ``True`` by default.

        In addition to the item, the configured settings for this plugin are
        supplied. The information provided by each of these arguments can be
        used to decide whether to accept the item.

        For example, the item's ``properties`` :class:`dict` may house meta data
        about the item, populated during collection. This data can be used to
        inform the acceptance logic.

        Example implementation:

        .. code-block:: python

            def accept(self, task_settings, item):

                accept = True

                # get the path for the item as set during collection
                path = item.properties["path"]

                # ensure the file is not too big
                size_in_bytes = os.stat(path).st_stize
                if size_in_bytes > math.pow(10, 9): # 1 GB
                    self.logger.warning("File is too big (> 1 GB)!")
                    accept = False

                return {"accepted": accepted}

        :param dict task_settings: The keys are strings, matching the keys returned
            in the :data:`settings` property. The values are
            :ref:`publish-api-setting` instances.
        :param item: The :ref:`publish-api-item` instance to process for
            acceptance.

        :returns: dictionary with boolean keys accepted, required and enabled
        """
        accept_data = {}

        # Only accept this item if we have its task settings dict
        if not task_settings:
            msg = "Unable to find task_settings for plugin: %s" % self.name
            accept_data["extra_info"] = {
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": msg
                }
            }
            accept_data["accepted"] = False
        else:
            accept_data["accepted"] = True

        return accept_data

    def validate(self, task_settings, item):
        """
        Validates the given item, ensuring it is ok to publish.

        Returns a boolean to indicate whether the item is ready to publish.
        Returning ``True`` will indicate that the item is ready to publish. If
        ``False`` is returned, the publisher will disallow publishing of the
        item.

        An exception can also be raised to indicate validation failed.
        When an exception is raised, the error message will be displayed as a
        tooltip on the task as well as in the logging view of the publisher.

        Simple implementation example for a Maya session item validation:

        .. code-block:: python

            def validate(self, task_settings, item):

                 path = cmds.file(query=True, sn=True)

                 # ensure the file has been saved
                 if not path:
                    raise Exception("The Maya session has not been saved.")

                 return True

        :param dict task_settings: The keys are strings, matching the keys returned
            in the :data:`settings` property. The values are
            :ref:`publish-api-setting` instances.
        :param item: The :ref:`publish-api-item` instance to validate.

        :returns: True if item is valid, False otherwise.
        """
        raise NotImplementedError

    def publish(self, task_settings, item):
        """
        Executes the publish logic for the given item and settings.

        Any raised exceptions will indicate that the publish pass has failed and
        the publisher will stop execution.

        Simple implementation example for a Maya session item publish:

        .. code-block:: python

            def publish(self, task_settings, item):

                path = item.properties["path"]

                # ensure the session is saved
                cmds.file(rename=path)
                cmds.file(save=True, force=True)

                # the hook's parent is the publisher
                publisher = self.parent

                # get the publish info
                publish_version = publisher.util.get_version_number(path)
                publish_name = publisher.util.get_publish_name(path)

                # register the publish and pack the publish info into the item's
                # properties dict
                sg_publish_data = sgtk.util.register_publish(
                    "tk": publisher.sgtk,
                    "context": item.context,
                    "comment": item.description,
                    "path": path,
                    "name": publish_name,
                    "version_number": publish_version,
                    "thumbnail_path": item.get_thumbnail_as_path(),
                    "published_file_type": "Maya Scene",
                    "dependency_paths": self._maya_get_session_depenencies()
                )

        :param dict task_settings: The keys are strings, matching the keys returned
            in the :data:`settings` property. The values are
            :ref:`publish-api-setting` instances.
        :param item: The :ref:`publish-api-item` instance to publish.
        """
        raise NotImplementedError

    def finalize(self, task_settings, item):
        """
        Execute the finalize logic for the given item and settings.

        This method can be used to do any type of cleanup or reporting after
        publishing is complete.

        Any raised exceptions will indicate that the finalize pass has failed
        and the publisher will stop execution.

        Simple implementation example for a Maya session item finalization:

        .. code-block:: python

            def finalize(self, task_settings, item):

                path = item.properties["path"]

                # get the next version of the path
                next_version_path = publisher.util.get_next_version_path(path)

                # save to the next version path
                cmds.file(rename=next_version_path)
                cmds.file(save=True, force=True)

        :param dict task_settings: The keys are strings, matching the keys returned
            in the :data:`settings` property. The values are
            :ref:`publish-api-setting` instances.
        :param item: The :ref:`publish-api-item` instance to finalize.
        """
        raise NotImplementedError

    def undo(self, task_settings, item):
        """
        Cleans up the products created after a publish for an item.

        This method can be used to delete any files or entities that were
        created as a part of the publish process.

        Any raised exceptions will have to be handled within this method itself.

        Simple implementation example of deleting a PublishedFile entity and the corresponding files on disk:

        .. code-block:: python

            def undo(self, task_settings, item):

                sg_publish_data_list = item.properties.get("sg_publish_data_list")
                publish_path = item.properties.get("publish_path")
                publish_symlink_path = item.properties.get("publish_symlink_path")

                if publish_symlink_path:
                    self._delete_files(publish_symlink_path, item)

                if publish_path:
                    self._delete_files(publish_path, item)

                if sg_publish_data_list:
                    for publish_data in sg_publish_data_list:
                        self.logger.info("Cleaning up published file...",
                                         extra={
                                             "action_show_more_info": {
                                                 "label": "Publish Data",
                                                 "tooltip": "Show the publish data.",
                                                 "text": "%s" % publish_data
                                             }
                                         }
                                         )
                        try:
                            self.sgtk.shotgun.delete(publish_data["type"], publish_data["id"])
                        except Exception:
                            self.logger.error(
                                "Failed to delete PublishedFile Entity for %s" % item.name,
                                extra={
                                    "action_show_more_info": {
                                        "label": "Show Error Log",
                                        "tooltip": "Show the error log",
                                        "text": traceback.format_exc()
                                    }
                                }
                            )
                    # pop the sg_publish_data_list too
                    item.properties.pop("sg_publish_data_list")

        :param dict task_settings: The keys are strings, matching the keys returned
            in the :data:`settings` property. The values are
            :ref:`publish-api-setting` instances.
        :param item: The :ref:`publish-api-item` instance to undo.
        """
        raise NotImplementedError

    ############################################################################
    # Methods for creating/displaying custom plugin interface

    # NOTE: We provide a default settings widget implementation here to show the
    # plugin's description. This allows for a consistent default look and
    # allows clients to write their own publish plugins while deferring custom
    # UI settings implementations until needed.

    def create_settings_widget(self, parent):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        on the right side of the publish UI).

        :param parent: The parent to use for the widget being created
        :return: A QtGui.QWidget or subclass that displays information about
            the plugin and/or editable widgets for modifying the plugin's
            settings.
        """

        # defer Qt-related imports
        from sgtk.platform.qt import QtGui

        # create a group box to display the description
        description_group_box = QtGui.QGroupBox(parent)
        description_group_box.setTitle("Description:")

        # The publish plugin that subclasses this will implement the
        # `description` property. We'll use that here to display the plugin's
        # description in a label.
        description_label = QtGui.QLabel(self.description)
        description_label.setWordWrap(True)
        description_label.setOpenExternalLinks(True)

        # create the layout to use within the group box
        description_layout = QtGui.QVBoxLayout()
        description_layout.addWidget(description_label)
        description_layout.addStretch()
        description_group_box.setLayout(description_layout)

        # return the description group box as the widget to display
        return description_group_box

    def get_ui_settings(self, widget):
        """
        Invoked by the publisher when the selection changes so the new settings
        can be applied on the previously selected tasks.

        The widget argument is the widget that was previously created by
        `create_settings_widget`.

        The method returns an dictionary, where the key is the name of a
        setting that should be updated and the value is the new value of that
        setting. Note that it is not necessary to return all the values from
        the UI. This is to allow the publisher to update a subset of settings
        when multiple tasks have been selected.

        Example::

            {
                 "setting_a": "/path/to/a/file"
            }

        :param widget: The widget that was created by `create_settings_widget`
        """

        # the default implementation does not show any editable widgets, so this
        # is a no-op. this method is required to be defined in order for the
        # custom UI to show up in the app
        return {}

    def set_ui_settings(self, widget, settings):
        """
        Allows the custom UI to populate its fields with the settings from the
        currently selected tasks.

        The widget is the widget created and returned by
        `create_settings_widget`.

        A list of settings dictionaries are supplied representing the current
        values of the settings for selected tasks. The settings dictionaries
        correspond to the dictionaries returned by the settings property of the
        hook.

        Example::

            settings = [
            {
                 "seeting_a": "/path/to/a/file"
                 "setting_b": False
            },
            {
                 "setting_a": "/path/to/a/file"
                 "setting_b": False
            }]

        The default values for the settings will be the ones specified in the
        environment file. Each task has its own copy of the settings.

        When invoked with multiple settings dictionaries, it is the
        responsibility of the custom UI to decide how to display the
        information. If you do not wish to implement the editing of multiple
        tasks at the same time, you can raise a ``NotImplementedError`` when
        there is more than one item in the list and the publisher will inform
        the user than only one task of that type can be edited at a time.

        :param widget: The widget that was created by `create_settings_widget`
        :param settings: a list of dictionaries of settings for each selected
            task.
        """

        # the default implementation does not show any editable widgets, so this
        # is a no-op. this method is required to be defined in order for the
        # custom UI to show up in the app
        pass

    ############################################################################
    # protected methods

    def _copy_files(self, dest_path, item):
        """
        This method handles copying an item's path(s) to a designated location.

        If the item has "sequence_paths" set, it will attempt to copy all paths
        assuming they meet the required criteria.
        """

        publisher = self.parent

        # ---- get a list of files to be copied
        if item.properties["is_sequence"]:
            work_files = item.properties.get("sequence_paths", [])
        else:
            work_files = [item.properties["path"]]

        # ---- copy the work files to the publish location
        processed_files = []

        seal_files = item.properties.get("seal_files", False)

        for work_file in work_files:

            if item.properties["is_sequence"]:
                frame_num = publisher.util.get_frame_number(work_file)
                dest_file = publisher.util.get_path_for_frame(dest_path, frame_num)
            else:
                dest_file = dest_path

            # If the file paths are the same, skip...
            if work_file == dest_file:
                continue

            # copy the file
            try:
                dest_folder = os.path.dirname(dest_file)
                ensure_folder_exists(dest_folder)
                copy_file(work_file, dest_file,
                          permissions=stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
                          seal=seal_files)
            except Exception as e:
                raise Exception(
                    "Failed to copy work file from '%s' to '%s'.\n%s" %
                    (work_file, dest_file, traceback.format_exc())
                )

            self.logger.debug(
                "Copied work file '%s' to '%s'." % (work_file, dest_file)
            )
            processed_files.append(dest_file)

        return processed_files

    def _symlink_files(self, item):
        """
        This method handles symlink an item's publish_path to publish_symlink_path,
        assuming publish_symlink_path is already populated.

        If the item has "sequence_paths" set, it will attempt to symlink all paths
        assuming they meet the required criteria.
        """

        publisher = self.parent

        source_path = item.properties["publish_path"]
        dest_path = item.properties["publish_symlink_path"]

        # ---- get a list of files to be symlinked
        if item.properties["is_sequence"]:
            work_files = item.properties.get("sequence_paths", [])
        else:
            work_files = [item.properties["path"]]

        # ---- symlink the publish files to the publish symlink path
        processed_files = []
        for work_file in work_files:

            if item.properties["is_sequence"]:
                frame_num = publisher.util.get_frame_number(work_file)
                source_file = publisher.util.get_path_for_frame(source_path, frame_num)
                dest_file = publisher.util.get_path_for_frame(dest_path, frame_num)
            else:
                source_file = source_path
                dest_file = dest_path

            # If the symlink paths and publish path are the same, skip...
            if dest_file == source_file:
                continue

            # symlink the file
            try:
                dest_folder = os.path.dirname(dest_file)
                ensure_folder_exists(dest_folder)
                symlink_file(source_file, dest_file)
            except Exception as e:
                raise Exception(
                    "Failed to symlink published file from '%s' to '%s'.\n%s" %
                    (source_file, dest_file, traceback.format_exc())
                )

            self.logger.debug(
                "Symlinked published file '%s' to '%s'." % (source_file, dest_file)
            )
            processed_files.append(dest_file)

        return processed_files

    def _delete_files(self, deletion_path, item):
        """
        This method handles deleting an item's path(s) from a designated location.

        If the item has "sequence_paths" set, it will attempt to delete all paths
        assuming they meet the required criteria.
        """

        publisher = self.parent

        # ---- get a list of files to be deleted
        if item.properties["is_sequence"]:
            work_files = item.properties.get("sequence_paths", [])
        else:
            work_files = [item.properties["path"]]

        # ---- delete the work files from the publish location
        processed_files = []
        for work_file in work_files:

            if item.properties["is_sequence"]:
                frame_num = publisher.util.get_frame_number(work_file)
                deletion_file = publisher.util.get_path_for_frame(deletion_path, frame_num)
            else:
                deletion_file = deletion_path

            # If the file paths are the same, skip...
            if work_file == deletion_file:
                continue

            # delete the file
            safe_delete_file(deletion_file)

            self.logger.debug(
                "Deleted publish file '%s'." % deletion_file
            )
            processed_files.append(deletion_file)

        return processed_files


    def _get_next_version_info(self, path, item, task_settings):
        """
        Return the next version of the supplied path.

        If templates are configured, use template logic. Otherwise, fall back to
        the zero configuration, path_info hook logic.

        :param str path: A path with a version number.
        :param item: The current item being published

        :return: A tuple of the form::

            # the first item is the supplied path with the version bumped by 1
            # the second item is the new version number
            (next_version_path, version)
        """

        if not path:
            self.logger.debug("Path is None. Can not determine version info.")
            return None, None

        publisher = self.parent

        next_version_path = publisher.util.get_next_version_path(path)
        cur_version = publisher.util.get_version_number(path)
        if cur_version:
            version = cur_version + 1
        else:
            version = None

        return next_version_path, version


    def _save_to_next_version(self, path, item, save_callback):
        """
        Save the supplied path to the next version on disk.

        :param path: The current path with a version number
        :param item: The current item being published
        :param save_callback: A callback to use to save the file

        Relies on the _get_next_version_info() method to retrieve the next
        available version on disk. If a version can not be detected in the path,
        the method does nothing.

        If the next version path already exists, logs a warning and does
        nothing.

        This method is typically used by subclasses that bump the current
        working/session file after publishing.
        """

        (next_version_path, version) = self._get_next_version_info(path, item)

        if version is None:
            self.logger.debug(
                "No version number detected in the publish path. "
                "Skipping the bump file version step."
            )
            return None

        self.logger.info("Incrementing file version number...")

        # nothing to do if the next version path can't be determined or if it
        # already exists.
        if not next_version_path:
            self.logger.warning("Could not determine the next version path.")
            return None
        elif os.path.exists(next_version_path):
            self.logger.warning(
                "The next version of the path already exists",
                extra={
                    "action_show_folder": {
                        "path": next_version_path
                    }
                }
            )
            return None

        # save the file to the new path
        save_callback(next_version_path)
        self.logger.info("File saved as: %s" % (next_version_path,))

        return next_version_path
