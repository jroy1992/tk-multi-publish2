# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk

from .base import PluginBase

from sgtk.platform.qt import QtCore, QtGui

HookBaseClass = sgtk.get_hook_baseclass()


class PublishPlugin(PluginBase):
    """
    This class defines the required interface for a publish plugin. Publish
    plugins are responsible for operating on items collected by the collector
    plugin. Publish plugins define which items they will operate on as well as
    the execution logic for each phase of the publish process.
    """

    class WidgetBaseClass(QtGui.QWidget):
        """
        Base Class for creating any custom settings widgets.
        """

        def __init__(self, creation_data, plugin, parent, *args):
            QtGui.QWidget.__init__(self, parent)

            initialization_strategy = creation_data["initialization_strategy"].value
            if initialization_strategy:
                if hasattr(plugin, initialization_strategy):
                    # call the strategy
                    getattr(plugin, initialization_strategy)(plugin, parent, *args)
                else:
                    plugin.logger.error("Couldn't find initialization strategy named %s." % initialization_strategy)

    class DescriptionWidget(WidgetBaseClass):
        """
        Widget to display description.
        """
        def __init__(self, creation_data, plugin, parent, *args):
            super(plugin.DescriptionWidget, self).__init__(creation_data, plugin, parent, *args)

            # The publish plugin that subclasses this will implement the
            # `description` property. We'll use that here to display the plugin's
            # description in a label.
            description_label = QtGui.QLabel(plugin.description)
            description_label.setWordWrap(True)
            description_label.setOpenExternalLinks(True)

            # create the layout to use within the group box
            description_layout = QtGui.QVBoxLayout()
            description_layout.addWidget(description_label)
            description_layout.addStretch()
            self.setLayout(description_layout)

    class PropertiesWidgetHandler(object):
        """
        Shows the editor widget with a label or checkbox depending on whether
        the widget is in multi-edit mode or not.

        When multiple values are available for this widget, the widget will by
        default be disabled and a checkbox will appear unchecked. By checking the
        checkbox, the user indicates they want to override the value with a specific
        one that will apply to all items.
        """

        def populate_data(self, qtwidgets, items, parent, field, editable, mode):

            self._editable = editable
            # we display only the value of the first item
            fields = items[0].properties.fields
            self._value = fields[field] if field in fields else "(None)"

            if len(items) > 1:
                # method that shows formmatted item names
                # field_name = field + "".join(["<br>&nbsp;&nbsp;&nbsp;&nbsp;- " + item.name for item in items])
                self._field_name = field + " (Multiple Values Exist)"
            else:
                self._field_name = field

        def value_changed(self):
            # TODO: Implement value validation before update.
            for item in self._items:
                item.properties.fields.update({self._field: self.widget.get_value()})

        def __init__(self, plugin, qtwidgets, items, parent, field, editable, mode="display"):
            """
            :param layout: Layout to add the widget into.
            :param text: Text on the left of the editor widget.
            :param editor: Widget used to edit the value.
            """
            # import the shotgun_fields module from the qtwidgets framework
            shotgun_fields = qtwidgets.import_module("shotgun_fields")
            self._layout = QtGui.QHBoxLayout()

            # initialize base data
            self._field = field
            self._field_name = field
            self._items = items
            self._value = "(Un-intialized)"
            # make it non-editable if the populate data doesn't modify it.
            self._editable = False

            self._color_mapping = {
                "display": None,
                "edit": sgtk.platform.constants.SG_STYLESHEET_CONSTANTS["SG_HIGHLIGHT_COLOR"],
                "error": sgtk.platform.constants.SG_STYLESHEET_CONSTANTS["SG_ALERT_COLOR"],
            }

            self.populate_data(qtwidgets, items, parent, field, editable, mode)

            self._field_label = shotgun_fields.text_widget.TextWidget(parent)  # QtGui.QLabel(field)

            self._editor = None
            self._display = None

            if isinstance(self._value, bool):
                self._display = shotgun_fields.checkbox_widget.CheckBoxWidget(parent)
                if self._editable:
                    self._editor = shotgun_fields.checkbox_widget.CheckBoxWidget(parent)
            elif isinstance(self._value, float):
                self._display = shotgun_fields.float_widget.FloatWidget(parent)
                if self._editable:
                    self._editor = shotgun_fields.float_widget.FloatEditorWidget(parent)
            elif isinstance(self._value, int) or isinstance(self._value, long):
                self._display = shotgun_fields.number_widget.NumberWidget(parent)
                if self._editable:
                    self._editor = shotgun_fields.number_widget.NumberEditorWidget(parent)
            # TODO: Implement a custom Combobox widget.
            # elif isinstance(self._value, list):
            #     self._display = shotgun_fields.list_widget.ListWidget(parent)
            #     if self._editable:
            #         self._editor = shotgun_fields.list_widget.ListEditorWidget(parent)
            elif isinstance(self._value, str):
                self._display = shotgun_fields.text_widget.TextWidget(parent)
                if self._editable:
                    self._editor = shotgun_fields.text_widget.TextEditorWidget(parent)
            else:
                self._display = shotgun_fields.text_widget.TextWidget(parent)

            if self._editable and self._editor:
                self._widget = shotgun_fields.shotgun_field_editable.ShotgunFieldEditable(self._display, self._editor,
                                                                                          parent)
                self._widget.enable_editing(self._editable)
                color = self._color_mapping.get(mode, None)
            else:
                self._widget = shotgun_fields.shotgun_field_editable.ShotgunFieldNotEditable(self._display, parent)
                # force the color to be display
                color = None

            if color:
                self._field_label.set_value("<b><font color='%s'>%s</font></b>" % (color, self._field_name))
            else:
                self._field_label.set_value("<b>%s</b>" % self._field_name)

            if len(items) > 1:
                # update tooltip on field to warn user about the force override if the value is changed.
                self._field_label.setToolTip("<p>%s</p>"
                                             "<p><b><font color='%s'>*Force overrides the same value "
                                             "on all selected items*</font></b></p>" % (self._field_label.get_value(),
                                                                                        self._color_mapping["error"]))

            # set the default value before connecting the signal
            self._widget.set_value(self._value)
            self._widget.value_changed.connect(lambda: self.value_changed())

            # self._field_label.setMinimumWidth(50)

            self._layout.addWidget(self._field_label)
            self._layout.addWidget(self._widget)
            self._layout.addStretch()

            parent.layout.addRow(self._layout)

        @property
        def widget(self):
            return self._widget

        @property
        def field(self):
            return self._field

        @property
        def value(self):
            return self._value

    @staticmethod
    def PropertiesWidgetInitialization(*args):
        """
        Dummy init for property widget, to be implemented by sub-class.
        """

        raise NotImplementedError

    class PropertiesWidget(WidgetBaseClass):
        """
        This is the plugin's custom UI.
        """

        def fill_cache(self, item, task, key, value):
            # set the first value for the key
            self._field_values_cache.setdefault(key, list())
            if value not in self._field_values_cache[key]:
                self._field_values_cache[key].append(value)
                self._field_items_cache.setdefault(key, list())
                self._field_items_cache[key].append(item)

        def fill_cache_missing_keys(self, item, task):
            # set the first value for the key
            for key in task.settings.cache["missing_keys"]:
                self._missing_items_cache.setdefault(key, list())
                self._missing_items_cache[key].append(item)

        def __init__(self, creation_data, plugin, parent, items_and_tasks, qtwidgets, *args):
            super(plugin.PropertiesWidget, self).__init__(creation_data, plugin, parent,
                                                          items_and_tasks, qtwidgets, *args)

            self.qtwidgets = qtwidgets

            self.layout = QtGui.QFormLayout(self)
            self.setLayout(self.layout)

            # since we only allow selection of tasks that have same context and same type, field keys should be same
            self._field_items_cache = dict()
            self._missing_items_cache = dict()
            self._field_values_cache = dict()
            self._field_widget_cache = dict()

            # get editable_fields from Settings To Display
            editable_fields = creation_data["editable_fields"]

            # get the cache ready to check for duplicate values across items
            [self.fill_cache(item, task, key, value) for item, task in items_and_tasks.iteritems()
             for key, value in item.properties.fields.iteritems()]

            for key, items in self._field_items_cache.iteritems():
                if key in editable_fields:
                    editable = True
                    mode = "edit"
                else:
                    editable = False
                    mode = "display"

                self._field_widget_cache.setdefault(key, list())

                self._field_widget_cache[key].append(plugin.PropertiesWidgetHandler(plugin, qtwidgets, items, self,
                                                                                    key, editable, mode=mode)
                                                     )

            # create the cache for missing keys
            [self.fill_cache_missing_keys(item, task) for item, task in items_and_tasks.iteritems()]

            for key, items in self._missing_items_cache.iteritems():
                self._field_widget_cache.setdefault(key, list())
                self._field_widget_cache[key].append(plugin.PropertiesWidgetHandler(plugin, qtwidgets, items, self,
                                                                                    key, editable=True,
                                                                                    mode="error")
                                                     )

    class SettingsWidgetHandler(PropertiesWidgetHandler):
        def populate_data(self, qtwidgets, tasks, parent, field, editable, color):

            self._editable = editable
            # we display only the value of the first item
            settings = tasks[0].settings
            self._value = settings[field].value if field in settings else "(None)"

            if len(tasks) > 1:
                # method that shows formmatted item names
                # field_name = field + "".join(["<br>&nbsp;&nbsp;&nbsp;&nbsp;- " + item.name for item in items])
                self._field_name = field + " (Multiple Values Exist)"
            else:
                self._field_name = field

        def value_changed(self):
            # TODO: Implement value validation before update.
            for task in self._items:
                task.settings[self._field].value = self.widget.get_value()

    class SettingsWidget(WidgetBaseClass):
        """
        This is the plugin's custom UI.
        """

        def fill_cache(self, tasks, key):
            # set the first value for the key
            self._field_values_cache.setdefault(key, list())
            for task in tasks:
                if key in task.settings and task.settings[key].value not in self._field_values_cache[key]:
                    self._field_values_cache[key].append(task.settings[key].value)
                    self._field_tasks_cache.setdefault(key, list())
                    self._field_tasks_cache[key].append(task)

        def __init__(self, creation_data, plugin, parent, items_and_tasks, qtwidgets, *args):
            super(plugin.SettingsWidget, self).__init__(creation_data, plugin, parent,
                                                        items_and_tasks, qtwidgets, *args)

            self.qtwidgets = qtwidgets

            self.layout = QtGui.QFormLayout(self)
            self.setLayout(self.layout)

            editable_settings = creation_data["exposed_settings"].value

            # since we only allow selection of tasks that have same context and same type, field keys should be same
            self._field_tasks_cache = dict()
            self._field_values_cache = dict()

            [self.fill_cache(items_and_tasks.values(), key) for key in editable_settings]

            for key, tasks in self._field_tasks_cache.iteritems():
                plugin.SettingsWidgetHandler(plugin, qtwidgets, tasks, self,
                                             key, editable=True, mode="edit"
                                             )

    class TabbedWidgetController(QtGui.QTabWidget):
        """
        Controller that creates the tabbed widgets.
        """

        def __init__(self, plugin, parent, items_and_tasks):
            QtGui.QTabWidget.__init__(self, parent)

            self.setTabPosition(QtGui.QTabWidget.South)

            qtwidgets = plugin.load_framework("tk-framework-qtwidgets_v2.x.x")

            items = items_and_tasks.keys()
            # since tasks will be of same type it's safe to assume they will all share the same "Settings To Display"
            tasks = items_and_tasks.values()

            task_settings = tasks[0].settings if len(tasks) else {}

            for tab_name, creation_data in task_settings.get("Settings To Display", {}).iteritems():
                if "type" not in creation_data:
                    plugin.logger.error("Type not defined in Settings To Display Tab Named %s." % tab_name)
                    continue

                if "initialization_strategy" not in creation_data:
                    plugin.logger.error("Initialization Strategy not "
                                        "defined in Settings To Display Tab Named %s." % tab_name)
                    continue

                widget_type = creation_data["type"].value

                if not hasattr(plugin, widget_type):
                    plugin.logger.error("Can't create Widget of Type %s. Please contact your TD." % widget_type)
                    continue

                widget_class = getattr(plugin, widget_type)
                widget_to_add = widget_class(creation_data, plugin, parent, items_and_tasks, qtwidgets)

                self.addTab(widget_to_add, tab_name)

    ############################################################################
    # Plugin properties

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
            },
            "Settings To Display": {
                "type": "dict",
                "default_value": {
                    "Description": {
                        "type": "DescriptionWidget",
                        "initialization_strategy": None,
                    },
                },
                "allows_empty": True,
                "description": "Dictionary of tab name, and it's corresponding widget type to use."
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
        return self.plugin.settings

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
        raise NotImplementedError

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
                    "dependency_paths": self._maya_get_session_dependencies()
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

                publisher = self.parent

                sg_publish_data_list = item.properties.get("sg_publish_data_list")
                publish_path = item.properties.get("publish_path")
                publish_symlink_path = item.properties.get("publish_symlink_path")

                if publish_symlink_path:
                    publisher.util.delete_files(publish_symlink_path, item)

                if publish_path:
                    publisher.util.delete_files(publish_path, item)

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

    def create_settings_widget(self, parent, items_and_tasks):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        on the right side of the publish UI).

        :param parent: The parent to use for the widget being created
        :param items_and_tasks: Items to create the settings widget for and their corresponding tasks.
        :return: A QtGui.QWidget or subclass that displays information about
            the plugin and/or editable widgets for modifying the plugin's
            settings.
        """
        # Give the control to TabWidgetController to manage creation of settings to display.
        tab_widget = self.TabbedWidgetController(self, parent, items_and_tasks)

        # return the description group box as the widget to display
        return tab_widget

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
