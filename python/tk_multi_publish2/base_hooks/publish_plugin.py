# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import collections
from operator import itemgetter

import sgtk
from sgtk import TankError, TankMissingTemplateError
from sgtk.platform.qt import QtCore, QtGui

from .base import PluginBase

HookBaseClass = sgtk.get_hook_baseclass()


class PublishPlugin(PluginBase):
    """
    This class defines the required interface for a publish plugin. Publish
    plugins are responsible for operating on items collected by the collector
    plugin. Publish plugins define which items they will operate on as well as
    the execution logic for each phase of the publish process.
    """
    class TabbedWidgetController(QtGui.QTabWidget):
        """
        Controller that creates the tabbed widgets.
        """
        def __init__(self, parent, hook, tasks):
            QtGui.QTabWidget.__init__(self, parent)

            # First add the description widget
            self.description_widget = PublishPlugin.DescriptionWidget(parent, hook)
            self.addTab(self.description_widget, "Description")

            # Next add the settings widget
            self.settings_widget = PublishPlugin.SettingsWidgetController(parent, hook, tasks)
            self.addTab(self.settings_widget, "Settings")

    class DescriptionWidget(QtGui.QWidget):
        """
        Widget to display the plugin description.
        """
        def __init__(self, parent, hook):
            QtGui.QWidget.__init__(self, parent)

            # The publish plugin that subclasses this will implement the
            # `description` property. We'll use that here to display the plugin's
            # description in a label.
            description_label = QtGui.QLabel(hook.plugin.description)
            description_label.setWordWrap(True)
            description_label.setOpenExternalLinks(True)

            # create the layout to use within the group box
            description_layout = QtGui.QVBoxLayout()
            description_layout.addWidget(description_label)
            description_layout.addStretch()
            self.setLayout(description_layout)

    class SettingsWidgetController(QtGui.QWidget):
        """
        Controller that creates the widgets for each setting.
        """
        def __init__(self, parent, hook, tasks):
            QtGui.QWidget.__init__(self, parent)
            plugin = hook.plugin

            self._layout = QtGui.QFormLayout(self)
            self.setLayout(self._layout)

            # since tasks will be of same type it's safe to assume they will all
            # share the same list of settings
            task_settings = tasks[0].settings if tasks else {}

            # TODO: these should probably be exceptions
            for setting in plugin.settings["Settings To Display"]:
                kwargs = setting.value

                setting_name = kwargs.pop("name", None)
                if not setting_name:
                    plugin.logger.error(
                        "Entry in 'Settings To Display' is missing its 'name' attribute")
                    continue

                setting = task_settings.get(setting_name)
                if not setting:
                    plugin.logger.error("Unknown setting: {}".format(setting_name))
                    continue

                widget_type = kwargs.pop("type", None)
                if not widget_type:
                    plugin.logger.error(
                        "No defined widget type for setting: {}".format(setting_name))
                    continue

                if not hasattr(hook, widget_type):
                    plugin.logger.error("Cannot find widget class: {}".format(widget_type))
                    continue

                # Instantiate the widget class
                widget_class = getattr(hook, widget_type)
                display_name = kwargs.get("display_name", setting_name)
                setting_widget = widget_class(self, hook, tasks, setting_name, **kwargs)
                setting_widget.setObjectName(setting_name)

                # Add a row entry
                self._layout.addRow(display_name, setting_widget)

    class SettingWidgetBaseClass(QtGui.QWidget):
        """
        Base Class for creating any custom settings widgets.
        """
        ErrorColor = sgtk.platform.constants.SG_STYLESHEET_CONSTANTS["SG_ALERT_COLOR"]
        NoneValue = "(None)"
        MultiplesValue = "<font color='{}'>{}</font>".format(ErrorColor, "(Multiple Values Exist)")

        def __init__(self, parent, hook, tasks, name, **kwargs):
            QtGui.QWidget.__init__(self, parent)

            self._hook = hook
            self._tasks = tasks
            self._name = name
            self._display_name = kwargs.get("display_name", name)
            self._editable = kwargs.get("editable", False)

            # Get the list of non None, sorted values
            values = [task.settings[name].value for task in self._tasks]
            values = filter(lambda x: x is not None, values)
            values.sort(reverse=True)

            # Get the number of unique values
            data_type = self._tasks[0].settings[name].type
            if data_type == "list":
                num_values = len(set([tuple(l) for l in values]))
            elif data_type == "dict":
                num_values = len(set([frozenset(d.items()) for d in values]))
            else:
                num_values = len(set(values))

            if num_values > 1:
                self._value = self.MultiplesValue
            elif num_values < 1:
                self._value = self.NoneValue
            else:
                self._value = values.pop()

        @classmethod
        def value_widget_factory(cls, name, value, editable=True):
            """
            Creates a standardized widget based on the value's type
            """
            # import the shotgun_fields module from the qtwidgets framework
            engine = sgtk.platform.current_engine()
            qtwidgets = sgtk.platform.framework.load_framework(
                engine, engine.context, engine.env, "tk-framework-qtwidgets_v2.x.x")
            shotgun_fields = qtwidgets.import_module("shotgun_fields")

            if isinstance(value, bool):
                display_widget = shotgun_fields.checkbox_widget.CheckBoxWidget(field_name=name)
                editor_widget = shotgun_fields.checkbox_widget.CheckBoxWidget(field_name=name)
            elif isinstance(value, float):
                display_widget = shotgun_fields.float_widget.FloatWidget(field_name=name)
                editor_widget = shotgun_fields.float_widget.FloatEditorWidget(field_name=name)
            elif isinstance(value, (int, long)):
                display_widget = shotgun_fields.number_widget.NumberWidget(field_name=name)
                editor_widget = shotgun_fields.number_widget.NumberEditorWidget(field_name=name)
            elif isinstance(value, str):
                display_widget = shotgun_fields.text_widget.TextWidget(field_name=name)
                editor_widget = shotgun_fields.text_widget.TextEditorWidget(field_name=name)
            # TODO: Implement a custom List Editor widget.
            # https://doc.qt.io/archives/qq/qq11-stringlistedit.html
            # elif isinstance(value, list):
            #     display_widget = shotgun_fields.list_widget.ListWidget(field_name=name)
            #     editor_widget = shotgun_fields.list_widget.ListEditorWidget(field_name=name)
            else:
                display_widget = shotgun_fields.text_widget.TextWidget(field_name=name)
                editor_widget = shotgun_fields.text_widget.TextEditorWidget(field_name=name)

            if editable:
                value_widget = shotgun_fields.shotgun_field_editable.ShotgunFieldEditable(
                    display_widget, editor_widget)
                value_widget.enable_editing(editable)
            else:
                value_widget = shotgun_fields.shotgun_field_editable.ShotgunFieldNotEditable(
                    display_widget)

            value_widget.set_value(value)

            # If there are multiple values, add a warning to the tooltip that changing
            # the value will change it for all entities.
            if value == cls.MultiplesValue:
                value_widget.setToolTip(
                    "<p>{}</p><p><b><font color='{}'>{}</font></b></p>".format(
                        "*Will overwrite the value for all selected entities*",
                        value,
                        cls.ErrorColor
                    )
                )
            return value_widget

        @property
        def name(self):
            """Return the setting name"""
            return self._name

        @property
        def value(self):
            """Return the setting value"""
            return self._value

    class SettingWidget(SettingWidgetBaseClass):
        """
        A widget class representing a generic setting.
        """
        def __init__(self, parent, hook, tasks, name, **kwargs):
            super(PublishPlugin.SettingWidget, self).__init__(
                parent, hook, tasks, name, **kwargs)

            self._layout = QtGui.QVBoxLayout(self)

            # Get the value_widget
            self._value_widget = self.value_widget_factory(
                self._name, self._value, self._editable)
            self._value_widget.setParent(self)

            # Add it to the layout
            self._layout.addWidget(self._value_widget)
            self._layout.addStretch()

            # connect the signal
            self._value_widget.value_changed.connect(self.value_changed)

        def value_changed(self):
            # TODO: Implement value validation before update.
            for task in self._tasks:
                task.settings[self._name].value = self._value_widget.get_value()

    class TemplateSettingWidget(SettingWidget):
        """
        A widget class representing a template setting.
        """
        TemplateField = collections.namedtuple("TemplateField",
            "name value editable is_missing")

        def __init__(self, parent, hook, tasks, name, **kwargs):
            super(PublishPlugin.SettingWidget, self).__init__(
                parent, hook, tasks, name, **kwargs)

            self._fields = {}
            self._resolved_value = ""

            self._layout = QtGui.QVBoxLayout(self)

            self._resolved_value_widget = QtGui.QLabel(self)
            self._layout.addWidget(self._resolved_value_widget)

            # Get the value_widget
            self._value_widget = self.value_widget_factory(
                self._name, self._value, self._editable)
            self._value_widget.setParent(self)

            # connect the signal
            self._value_widget.value_changed.connect(self.value_changed)

            # TODO: dump this in a collapsible widget
            self._fields_layout = QtGui.QFormLayout()
            self._layout.addLayout(self._fields_layout)

            # Add the value to the fields layout
            self._fields_layout.addRow("Template Name", self._value_widget)

            # Gather the fields used to resolve the template
            self.gather_fields()

            # Calculate the resolved template value
            self.resolve_template_value()

            # Cache the data
            self.cache_data()

            # Update the ui
            self.refresh_ui()

        @property
        def fields(self):
            """Return the setting fields"""
            return self._fields

        @property
        def resolved_value(self):
            """Return the setting resolved value"""
            return self._resolved_value

        def value_changed(self):
            """
            Handle when the template value has changed
            """
            super(PublishPlugin.TemplateSettingWidget, self).value_changed()

            # Regather the fields used to resolve the template
            self.gather_fields()

            # Recalculate the resolved template value
            self.resolve_template_value()

            # Recache the data
            self.cache_data()

            # Update the ui
            self.refresh_ui()

        def field_changed(self):
            """
            Handle when a field value has changed
            """
            field_name = self.sender().get_field_name()
            field_value = self.sender().get_value()

            # Update the fields dictionary with the widget value
            self._fields[field_name] = self._fields[field_name]._replace(
                value=field_value, is_missing=False)

            # Recalculate the resolved template value
            self.resolve_template_value()

            # Recache the data
            self.cache_data()

            # Update the ui
            self._resolved_value_widget.setText(self._resolved_value)

        def gather_fields(self):
            """
            Gather the list of template fields
            """
            publisher = self._hook.parent

            # Gather the fields for every input task
            fields = {}
            for task in self._tasks:
                value = task.settings[self._name].value
                if value is None:
                    continue

                tmpl = publisher.get_template_by_name(value)
                if not tmpl:
                    # this template was not found in the template config!
                    raise TankMissingTemplateError(
                        "The Template '%s' does not exist!" % value)

                # Get the list of fields specific to this template
                tmpl_keys = tmpl.keys.keys()

                # First get the fields from the context
                # We always recalculate this because the context may have changed
                # since the last time the cache was updated.
                try:
                    context_fields = task.item.context.as_template_fields(tmpl)
                except TankError:
                    self._hook.plugin.logger.error(
                        "Unable to get context fields for template: %s", value)
                else:
                    for k, v in context_fields.iteritems():
                        if k not in tmpl_keys:
                            continue
                        if k in fields:
                            if fields[k].value != v:
                                fields[k].value = self.MultiplesValue
                        else:
                            fields[k] = self.TemplateField(
                                k, v, editable=False, is_missing=False)

                # Next get any cached fields
                if "fields" in task.settings[self._name].extra:
                    for k, v in task.settings[self._name].extra["fields"].iteritems():
                        if k not in tmpl_keys:
                            continue
                        if k in fields:
                            if fields[k].value != v.value:
                                fields[k].value = self.MultiplesValue
                        else:
                            fields[k] = v

                # Next get the list of missing fields
                tmpl_fields = dict([(k, v.value) for k, v in fields.iteritems()])
                missing_keys = tmpl.missing_keys(tmpl_fields, True)
                for k in missing_keys:
                    if k in fields:
                        if fields[k].value is not None:
                            fields[k].value = self.MultiplesValue
                            fields[k].is_missing = True
                    else:
                        fields[k] = self.TemplateField(
                            k, None, editable=True, is_missing=True)

            # Now pickup any overridden values already set via the UI
            for field in fields.iterkeys():
                if field in self._fields:
                    fields[field] = self._fields[field]

            # Now update the member dict
            self._fields = fields

        def resolve_template_value(self):
            """
            Resolve the template value
            """
            publisher = self._hook.parent

            # Reset the value
            self._resolved_value = ""

            # If no template defined or not all are the same, just bail
            if self._value in (self.NoneValue, self.MultiplesValue):
                self._resolved_value = self._value
                return

            # If we are missing any keys, let the user know so they can fill them in.
            if any([f.is_missing for f in self._fields.itervalues()]):
                self._resolved_value = "Cannot resolve template. Missing field values!"
                return

            tmpl = publisher.get_template_by_name(self._value)
            if not tmpl:
                # this template was not found in the template config!
                raise TankMissingTemplateError(
                    "The Template '%s' does not exist!" % self._value)

            # Create the flattened list of fields to apply
            fields = {}
            ignore_types = []
            for field in self._fields.itervalues():
                if field.value == self.MultiplesValue:
                    fields[field.name] = "{%s}" % field.name
                    ignore_types.append(field.name)
                else:
                    fields[field.name] = field.value

            # Apply fields to template
            self._resolved_value = tmpl.apply_fields(fields, ignore_types=ignore_types)

        def cache_data(self):
            """Store persistent data on the settings object"""
            for task in self._tasks:
                # Store the resolved value in the "extra" section of the settings obj
                task.settings[self._name].extra["resolved_value"] = self._resolved_value

                # Store the field values in the "extra" section of the settings obj
                if "fields" not in task.settings[self._name].extra:
                    task.settings[self._name].extra["fields"] = {}
                task.settings[self._name].extra["fields"].update(self._fields)

        def refresh_ui(self):
            """Update the UI"""
            self._resolved_value_widget.setText(self._resolved_value)

            # Clear the list of fields, excluding the template name
            for i in reversed(range(self._fields_layout.count())[2:]):
                field_widget = self._fields_layout.itemAt(i).widget()
                self._fields_layout.removeWidget(field_widget)
                field_widget.deleteLater()

            # And repopulate it
            for field in sorted(self._fields.itervalues(), key=itemgetter(2, 3, 0)):
                # Create the field widget
                field_widget = self.value_widget_factory(
                    field.name, field.value, field.editable)
                field_widget.setObjectName(field.name)
                field_widget.setParent(self)

                # Add a row entry
                self._fields_layout.addRow(field.name, field_widget)

                # connect the signal
                field_widget.value_changed.connect(self.field_changed)


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
                "type": "list",
                "values": {
                    "type": "dict"
                },
                "default_value": [],
                "allows_empty": True,
                "description": (
                    "A list of settings to display in the UI. Each entry in the "
                    "list is a dict that defines the associated widget name and "
                    "class to use, as well as any keyword arguments to pass to the "
                    "constructor."
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

    def create_settings_widget(self, parent, tasks):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        on the right side of the publish UI).

        :param parent: The parent to use for the widget being created
        :param tasks: List of tasks to create the settings widget for.
        :return: A QtGui.QWidget or subclass that displays information about
            the plugin and/or editable widgets for modifying the plugin's
            settings.
        """
        # Give the control to TabWidgetController to manage creation of settings to display.
        tab_widget = self.TabbedWidgetController(parent, self, tasks)

        # return the description group box as the widget to display
        return tab_widget

    def get_ui_settings(self, widget):
        """
        Invoked by the publisher when the selection changes so the new settings
        can be applied on the previously selected tasks.

        The widget argument is the widget that was previously created by
        `create_settings_widget`.

        The method returns a dictionary, where the key is the name of a
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
                 "setting_a": "/path/to/a/file"
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
