# Copyright (c) 2018 Shotgun Software Inc.
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

from sgtk.platform.qt import QtCore, QtGui
from sgtk.platform.validation import convert_string_to_type

from sgtk import TankError, TankMissingTemplateError
from .base import PluginBase


class CollectorPlugin(PluginBase):
    """
    This class defines the required interface for a collector plugin.
    Collectors are used to gather individual files that are loaded via the
    file browser or dragged and dropped into the Publish2 UI. It is also used
    to gather items to be published within the current DCC session.
    """
    class PropertiesWidgetController(QtGui.QWidget):
        """
        Controller that creates the widgets for each item property.
        """
        # Signal for when a property value has changed
        property_changed = QtCore.Signal()

        def __init__(self, parent, hook, items):
            QtGui.QWidget.__init__(self, parent)
            plugin = hook.plugin

            self._layout = QtGui.QFormLayout(self)

            for setting in plugin.settings["Properties To Display"]:
                kwargs = setting.value

                # TODO: this should probably be an exception
                name = kwargs.pop("name", None)
                if not name:
                    plugin.logger.error(
                        "Entry in 'Properties To Display' is missing its 'name' attribute")
                    continue

                widget_type = kwargs.pop("type", None)
                if not widget_type:
                    plugin.logger.error(
                        "No defined widget type for setting: {}".format(name))
                    continue

                if not hasattr(hook, widget_type):
                    plugin.logger.error("Cannot find widget class: {}".format(widget_type))
                    continue

                # Instantiate the widget class
                widget_class = getattr(hook, widget_type)
                display_name = kwargs.get("display_name", name)
                property_widget = widget_class(self, hook, items, name, **kwargs)
                property_widget.setObjectName(name)

                # Add a row entry
                self._layout.addRow(display_name, property_widget)

    class PropertyWidget(PluginBase.ValueWidgetBaseClass):
        """
        A widget class representing an item property.
        """
        # Signal for when a property value has changed
        value_changed = QtCore.Signal()

        def __init__(self, parent, hook, items, name, **kwargs):

            self._items = items

            # Get the list of non None, sorted values
            values = [item.properties.get(name) for item in self._items]
            values = filter(lambda x: x is not None, values)
            values.sort(reverse=True)

            # Get the number of unique values
            value_type = kwargs.pop("type", type(values[0]).__name__)
            if value_type == "list":
                num_values = len(set([tuple(l) for l in values]))
            elif value_type == "dict":
                num_values = len(set([frozenset(d.items()) for d in values]))
            else:
                num_values = len(set(values))

            if num_values > 1:
                value = self.MultiplesValue
            elif num_values < 1:
                value = None
            else:
                value = values.pop()

            super(CollectorPlugin.PropertyWidget, self).__init__(
                parent, hook, name, value, value_type, **kwargs)

            self._layout = QtGui.QVBoxLayout(self)

            # Get the value_widget
            self._value_widget = self.value_widget_factory(
                self._name, self._value, self._value_type, self._editable)
            self._value_widget.setParent(self)

            # Add it to the layout
            self._layout.addWidget(self._value_widget)
            self._layout.addStretch()

            # Connect the signal
            self._value_widget.value_changed.connect(self.update_value)

            # Connect to the property_changed signal so external processes can
            # react accordingly (i.e. rerun init_task_settings)
            self.value_changed.connect(parent.property_changed)

#        @QtCore.Slot()
        def update_value(self):

            # The sender is a value widget
            value_widget = self.sender()
            field_name = value_widget.get_field_name()

            # TODO: Implement value validation before update.
            self._value = value_widget.get_value()

            # Convert any NoneStr values or empty strings to real None
            if self._value in (self.NoneValue, ""):
                self._value = None
            # Else ensure that we are casting the value to its correct type
            elif self._value != self.MultiplesValue:
                value_type = type(self._value).__name__
                if value_type != self._value_type:
                    if value_type == "str":
                        self._value = convert_string_to_type(self._value, self._value_type)
                    else:
                        raise TypeError(
                            "Unknown conversion from type '{}' to '{}'".format(
                                value_type, self._value_type))

            # If this is coming from a different widget, we need to update
            # this widget with the value
            if value_widget is not self._value_widget:
                signals_blocked = self._value_widget.blockSignals(True)
                try:
                    if self._value == self.MultiplesValue:
                        self._value_widget.set_value(self.MultiplesStr)
                    elif self._value == self.NoneValue:
                        self._value_widget.set_value(self.NoneStr)
                    else:
                        self._value_widget.set_value(self._value)
                finally:
                    self._value_widget.blockSignals(signals_blocked)

            # Emit that our value has changed
            self.value_changed.emit()

            # Cache out the value
            for item in self._items:
                if self._value == self.MultiplesValue:
                    # Skip caching the value if its a multiple
                    continue
                # Only overwrite valid values
                item.properties[self._name] = self._value

        @property
        def items(self):
            return self._items

    class FieldsWidget(PropertyWidget):
        """
        A widget class representing a template setting.
        """
        TemplateField = collections.namedtuple("TemplateField",
                                               "name value type editable is_missing")

        # Signal for when a setting field has changed
        field_changed = QtCore.Signal(TemplateField)

        def __init__(self, parent, hook, items, name, **kwargs):

            super(CollectorPlugin.FieldsWidget, self).__init__(
                parent, hook, items, name, **kwargs)

            self._fields = {}
            self._field_widgets = {}
            self._resolved_value = ""

            # by default we will assume that this widget can utilise template type task settings
            # this will be used to get the template names, to derive the missing keys and context fields for an item
            self._template_source_setting_name = kwargs.pop("template_source_setting_name", "publish_path_template")

            # TODO: dump this in a collapsible widget
            self._resolved_value_widget = QtGui.QLabel(self)
            self._layout.addWidget(self._resolved_value_widget)

            relevant_task_settings = [task.settings[setting] for task in items[0]._tasks for setting in task.settings
                                      if self._template_source_setting_name in task.settings[setting].name]
            # Get the value_widget
            self._value_widget = self.value_widget_factory(
                self._template_source_setting_name, self._value, self._value_type, self._editable)
            self._value_widget.setParent(self)

            # Connect the value_changed signal to the property_changed signal so
            # all other properties will be notified about the change
            self._value_widget.value_changed.connect(parent.property_changed)

            # Connect the property_changed signal to the update_value slot so that
            # this widget will update whenever any property is changed.
            parent.property_changed.connect(self.update_value)

            # TODO: dump this in a collapsible widget
            self._fields_layout = QtGui.QFormLayout()
            self._fields_layout.setContentsMargins(0, 0, 0, 0)
            self._fields_layout.setVerticalSpacing(1)
            self._layout.addLayout(self._fields_layout)

            # Add the value to the fields layout
            self._fields_layout.addRow("Template Name", self._value_widget)

            # Gather the fields used to resolve the template
            self.gather_fields()

            # Calculate the resolved template value
            # self.resolve_template_value()

            # Cache the data
            self.cache_data()

            # Update the ui
            self.refresh_ui()

        @property
        def fields(self):
            """Return the property fields"""
            return self._fields

        @property
        def resolved_value(self):
            """Return the property resolved value"""
            return self._resolved_value

        def update_value(self):
            """
            Handle when the template value has changed
            """
            # The sender is the controller widget, which received its signal
            # from a PropertyWidget value_widget
            value_widget = self.sender().sender()
            field_name = value_widget.get_field_name()

            # Ensure the signal isn't from a field widget
            if field_name in self._field_widgets:
                return

            value = self._value
            super(CollectorPlugin.FieldsWidget, self).update_value()
            if value == self._value:
                # Bail if the value didn't actually change
                return

            # Regather the fields used to resolve the template
            self.gather_fields()

            # Recalculate the resolved template value
            # self.resolve_template_value()

            # Recache the data
            self.cache_data()

            # Update the ui
            self.refresh_ui()

        def update_field(self):
            """
            Handle when a field value has changed
            """
            do_full_refresh = False

            # The sender is the controller widget, which received its signal
            # from a PropertyWidget value_widget/field_widget
            field_widget = self.sender().sender()

            field_name = field_widget.get_field_name()
            field_value = field_widget.get_value()

            # If the sender is from another property, check that the field matches
            # one of this property's linked fields, else ignore
            if field_name not in self._field_widgets or field_widget.parent() is not self:
                return

            # Convert any NoneStr values or empty strings to real None
            if field_value in (self.NoneValue, ""):
                field_value = None
            # Else ensure that we are casting the value to its correct type
            elif field_value != self.MultiplesValue:
                value_type = type(field_value).__name__
                field_type = self._fields[field_name].type
                if value_type != field_type:
                    if value_type == "str":
                        field_value = convert_string_to_type(field_value, field_type)
                        # Need to replace the field widget for this guy, so do a
                        # full refresh
                        do_full_refresh = True
                    else:
                        raise TypeError(
                            "Unknown conversion from type '{}'' to '{}'".format(
                                value_type, field_type))

            # If this is coming from a linked property, we need to update
            # the widget as well
            if field_widget is not self._field_widgets[field_name]:
                signals_blocked = self._field_widgets[field_name].blockSignals(True)
                try:
                    if field_value == self.MultiplesValue:
                        self._field_widgets[field_name].set_value(self.MultiplesStr)
                    elif field_value == self.NoneValue:
                        self._field_widgets[field_name].set_value(self.NoneStr)
                    else:
                        self._field_widgets[field_name].set_value(field_value)
                finally:
                    self._field_widgets[field_name].blockSignals(signals_blocked)

            # Update the fields dictionary with the new value
            self._fields[field_name] = self._fields[field_name]._replace(
                value=field_value, is_missing=False)

            # Emit that our field value has changed
            self.field_changed.emit(self._fields[field_name])

            # Recalculate the resolved template value
            # self.resolve_template_value()

            # Recache the data
            self.cache_data()

            # Update the ui
            if do_full_refresh:
                self.refresh_ui()
            # else:
            #     self._resolved_value_widget.setText(self._resolved_value)

        def gather_fields(self):
            """
            Gather the list of template fields
            """
            publisher = self._hook.parent

            # Gather the fields for every input task
            fields = {}
            for item in self._items:
                relevant_task_settings = [task.settings[setting] for task in item._tasks for setting in task.settings
                                          if self._template_source_setting_name in task.settings[setting].name]

                if len(relevant_task_settings) != 1:
                    # we assume that all the fields relevant to the item will be present in only one setting name.
                    continue
                else:
                    setting = relevant_task_settings[0]
                    value = setting.value
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
                        context_fields = item.context.as_template_fields(tmpl)
                    except TankError:
                        self._hook.plugin.logger.error(
                            "Unable to get context fields for template: %s", value)
                    else:
                        for k, v in context_fields.iteritems():
                            if k not in tmpl_keys:
                                continue
                            if k in fields:
                                if fields[k].value != v:
                                    fields[k] = fields[k]._replace(
                                        value=self.MultiplesValue, is_missing=False)
                            else:
                                fields[k] = self.TemplateField(
                                    k, v, "str", editable=False, is_missing=False)

                    # Next get any cached fields
                    if "fields" in setting.extra:
                        for k, v in setting.extra["fields"].iteritems():
                            if k not in tmpl_keys:
                                continue
                            if k in fields:
                                if fields[k].value != v.value:
                                    fields[k] = fields[k]._replace(
                                        value=self.MultiplesValue, is_missing=False)
                            else:
                                fields[k] = v

                    # Next get the list of missing fields
                    tmpl_fields = dict([(k, v.value) for k, v in fields.iteritems()])
                    missing_keys = tmpl.missing_keys(tmpl_fields, True)
                    for k in missing_keys:
                        if k in fields:
                            if fields[k].value is not None:
                                fields[k]._replace(
                                    value=self.MultiplesValue, is_missing=True)
                        else:
                            fields[k] = self.TemplateField(
                                k, None, "str", editable=True, is_missing=True)

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
            if self._value is None:
                self._resolved_value = self.NoneStr
                return
            elif self._value == self.MultiplesValue:
                self._resolved_value = self.MultiplesStr
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
            for item in self._items:
                for name, field in self._fields.iteritems():
                    if field.value == self.MultiplesValue or not field.editable:
                        # Don't override value with multiples key,
                        # or even keys that are not editable.
                        continue
                    # update the item.properties.fields
                    item.properties[self._name][name] = field.value

                # settings update doesn't happen in init_task_settings, coz it returns a new settings object :\
                for task in item._tasks:
                    # Initialize the fields dictionary for any template settings
                    for setting in task.settings.itervalues():
                        if setting.type == "template":
                            setting.extra.setdefault("fields", {})

                            # Add in any relevant keys stored on the item
                            for k, v in item.properties.get("fields", {}).iteritems():
                                setting.extra["fields"][k] = \
                                    self.TemplateField(k, v, "str", editable=True, is_missing=False)

                            # Add in the version key if applicable
                            setting.extra["fields"]["version"] = \
                                self.TemplateField("version", item.properties.fields["version"],
                                                   "str", editable=True, is_missing=False)

        def refresh_ui(self):
            """Update the UI"""
            # self._resolved_value_widget.setText(self._resolved_value)

            # Clear the list of fields, excluding the template name
            for i in reversed(range(self._fields_layout.count())[2:]):
                field_widget = self._fields_layout.itemAt(i).widget()
                self._fields_layout.removeWidget(field_widget)
                field_widget.deleteLater()

            # And repopulate it
            self._field_widgets = {}
            for field in sorted(self._fields.itervalues(), key=itemgetter(2, 3, 0)):
                # Create the field widget
                field_widget = self.value_widget_factory(
                    field.name, field.value, field.type, field.editable)
                field_widget.setObjectName(field.name)
                field_widget.setParent(self)

                field_name = field.name

                # Add a row entry
                self._fields_layout.addRow(field_name, field_widget)
                self._field_widgets[field.name] = field_widget

                # Connect the value_changed signal to the property_changed signal so
                # all other properties will be notified about the change
                field_widget.value_changed.connect(self.parent().property_changed)

                # Connect the property_changed signal to the update_field slot so that
                # this widget will update whenever any property is changed.
                self.parent().property_changed.connect(self.update_field)

    ############################################################################
    # Collector properties

    @property
    def settings_schema(self):
        """
        A :class:`dict` defining the configuration interface for this collector.

        The values configured for the collector will be supplied via settings
        parameter in the :func:`process_current_session` and
        :func:`process_file` methods.

        The dictionary can include any number of settings required by the
        collector, and takes the form::

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
                    "Work Template": {
                        "type": "template",
                        "default": None,
                        "description": "A work file template required by this collector."
                    },
                    "Exclude Objects": {
                        "type": "list",
                        "default": ["obj1", "obj2", "obj3"],
                        "description": "A list of objects to ignore."
                    }
                }

        The settings are exposed via the ``collector_settings`` setting in the
        app's configuration. Example::

            collector_settings:
                Work Template: my_work_template
                Exclude Objects: [obj1, obj4]

        .. note:: See the hooks defined in the publisher app's ``hooks/`` folder
           for additional example implementations.
        """
        return {
            "Item Types": {
                "type": "dict",
                "values": {
                    "type": "dict",
                },
                "default_value": {},
                "description": (
                    "Dictionary of item types that the collector will attempt to "
                    "match and create instances of."
                )
            },
            "Properties To Display": {
                "type": "list",
                "values": {
                    "type": "dict"
                },
                "default_value": [
                    {
                        "name": "fields",
                        "display_name": "Item Fields",
                        "editable": False,
                        "template_source_setting_name": "publish_path_template",
                        "type": "FieldsWidget"
                    },
                ],
                "allows_empty": True,
                "description": (
                    "A list of properties to display in the UI. Each entry in the list is a dict "
                    "that defines the associated property name, the widget class to use, as well "
                    "as any keyword arguments to pass to the constructor."
                ),
            }
        }

    ############################################################################
    # Collection methods

    def process_current_session(self, settings, parent_item):
        """
        This method analyzes the current engine session and creates a hierarchy
        of items for publishing.

        A typical implementation of this method would create an item that
        represents the current session (e.g. the current Maya file) or all open
        documents in a multi-document scenario (such as Photoshop). Top level
        items area created as children of the supplied ``parent_item``
        (a :ref:`publish-api-item` instance).

        Any additional items, specific to the current session, can then be
        created as children of the session item. This is not a requirement
        however. You could, for example, create a flat list of items, all
        sharing the same parent.

        The image below shows a Maya scene item with a child item that
        represents a playblast to be published. Each of these items has one or
        more publish tasks attached to them.

        .. image:: ./resources/collected_session_item.png

        |

        The ``settings`` argument is a dictionary where the keys are the names
        of the settings defined by the :func:`settings` property and the values
        are :ref:`publish-api-setting` instances as configured for this
        instance of the publish app.

        To create items within this method, use the
        :meth:`~.api.PublishItem.create_item` method available on the supplied
        ``parent_item``.

        Example Maya implementation:

        .. code-block:: python

            def process_current_session(settings, parent_item):

                path = cmds.file(query=True, sn=True)

                session_item = parent_item.create_item(
                    "maya.session",
                    "Maya Session",
                    os.path.basename(path)
                )

                # additional work here to prep the session item such as defining
                # an icon, populating the properties dictionary, etc.
                session_item.properties["path"] = path

                # collect additional file types, parented under the session
                self._collect_geometry(settings, session_item)

        .. note:: See the hooks defined in the publisher app's ``hooks/`` folder
           for additional example implementations.

        :param dict settings: A dictionary of configured
            :ref:`publish-api-setting` objects for this collector.
        :param parent_item: The root :ref:`publish-api-item` instance to
            collect child items for.
        """
        raise NotImplementedError

    def create_properties_widget(self, parent, items):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        that is used to display Item Details).

        :param parent: The parent to use for the widget being created.
        :param items: List of items to create the Settings tab for.
        :return: A QtGui.QWidget or subclass that displays information about
            the item and/or editable widgets for modifying the item's
            properties.
        """

        if not len(self.plugin.settings["Properties To Display"].value):
            no_properties_to_display = QtGui.QLabel(parent)
            no_properties_to_display.setAlignment(QtCore.Qt.AlignCenter)
            no_properties_to_display.setObjectName("no_properties_to_display")
            no_properties_to_display.setText("No Properties to display for the selected items.")
            widget = no_properties_to_display
        else:
            widget = CollectorPlugin.PropertiesWidgetController(parent, self, items)

        return widget


    def process_file(self, settings, parent_item, path):
        """
        This method creates one or more items to publish for the supplied file
        path.

        The image below shows a collected text file item to be published.

        .. image:: ./resources/collected_file.png

        |

        A typical implementation of this method involves processing the supplied
        path to determine what type of file it is and how to display it before
        creating the item to publish.

        The ``settings`` argument is a dictionary where the keys are the names
        of the settings defined by the :func:`settings` property and the values
        are :ref:`publish-api-setting` instances as
        configured for this instance of the publish app.

        To create items within this method, use the
        :meth:`~.api.PublishItem.create_item` method available on the supplied
        ``parent_item``.

        Example implementation:

        .. code-block:: python

            def process_file(settings, parent_item, path):

                # make sure the path is normalized. no trailing separator,
                # separators are appropriate for the current os, no double
                # separators, etc.
                path = sgtk.util.ShotgunPath.normalize(path)

                # do some processing of the file to determine its type, and how
                # to display it.
                ...

                # create and populate the item
                file_item = parent_item.create_item(
                    item_type,
                    type_display,
                    os.path.basename(path)
                )

                # additional work here to prep the session item such as defining
                # an icon, populating the properties dictionary, etc.
                session_item.properties["path"] = path

        .. note:: See the hooks defined in the publisher app's ``hooks/`` folder
           for additional example implementations.

        :param dict settings: A dictionary of configured
            :ref:`publish-api-setting` objects for this collector.
        :param parent_item: The root :ref:`publish-api-item` instance to
            collect child items for.
        :param path: A string representing the file path to analyze
        """
        raise NotImplementedError


    def on_context_changed(self, settings, item):
        """
        Callback to update the item on context changes.

        :param dict settings: A dictionary of configured
            :ref:`publish-api-setting` objects for this
            collector.
        :param parent_item: The current :ref:`publish-api-item` instance
            whose :class:`sgtk.Context` has been updated.
        """
        raise NotImplementedError
