# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from sgtk.platform.qt import QtCore, QtGui
from sgtk.platform.validation import convert_string_to_type

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

                # Instantiate the widget class
                display_name = kwargs.get("display_name", name)
                property_widget = CollectorPlugin.PropertyWidget(self, hook, items, name, **kwargs)
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
            values = [items.properties.get(name) for item in self._items]
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
