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
from sgtk.platform.qt import QtCore, QtGui

HookBaseClass = sgtk.get_hook_baseclass()

class PluginBase(HookBaseClass):
    """
    Base Plugin class.
    """
    class ValueWidgetBaseClass(QtGui.QWidget):
        """
        Base Class for creating any custom settings widgets.
        """
        WarnColor = sgtk.platform.constants.SG_STYLESHEET_CONSTANTS["SG_HIGHLIGHT_COLOR"]
        ErrorColor = sgtk.platform.constants.SG_STYLESHEET_CONSTANTS["SG_ALERT_COLOR"]
        MultiplesValue = "(Multiple Values Exist)"
        MultiplesStr = "<font color='{}'>{}</font>".format(WarnColor, MultiplesValue)
        NoneValue = "(None)"
        NoneStr = "<font color='{}'>{}</font>".format(ErrorColor, NoneValue)

        def __init__(self, parent, hook, name, value, value_type=None, **kwargs):
            QtGui.QWidget.__init__(self, parent)

            self._hook = hook
            self._name = name
            self._value = value
            self._value_type = value_type or type(value).__name__
            self._display_name = kwargs.pop("display_name", name)
            self._editable = kwargs.pop("editable", False)

        @classmethod
        def value_widget_factory(cls, name, value, value_type=None, editable=True):
            """
            Creates a standardized widget based on the value's type
            """
            value = cls.NoneValue if value is None else value
            # Specify an alternate value type, useful when value is None
            value_type = value_type or type(value).__name__

            # import the shotgun_fields module from the qtwidgets framework
            engine = sgtk.platform.current_engine()
            qtwidgets = sgtk.platform.framework.load_framework(
                engine, engine.context, engine.env, "tk-framework-qtwidgets_v2.x.x")
            shotgun_fields = qtwidgets.import_module("shotgun_fields")

            if value_type == "bool":
                display_widget = shotgun_fields.checkbox_widget.CheckBoxWidget(field_name=name)
                editor_widget = shotgun_fields.checkbox_widget.CheckBoxWidget(field_name=name)
            elif value_type == "float":
                display_widget = shotgun_fields.float_widget.FloatWidget(field_name=name)
                editor_widget = shotgun_fields.float_widget.FloatEditorWidget(field_name=name)
            elif value_type in ("int", "long"):
                display_widget = shotgun_fields.number_widget.NumberWidget(field_name=name)
                editor_widget = shotgun_fields.number_widget.NumberEditorWidget(field_name=name)
            elif value_type == "str":
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

            # Add some HTML formatting for Multiples and None
            if value == cls.MultiplesValue:
                value_widget.set_value(cls.MultiplesStr)
            elif value == cls.NoneValue:
                value_widget.set_value(cls.NoneStr)
            else:
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

    def __init__(self, parent, plugin=None, **kwargs):
        """
        Construction
        """
        # call base init
        super(PluginBase, self).__init__(parent, **kwargs)

        # initialize plugin
        self.__plugin = plugin

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
    def settings_schema(self):
        """
        Dictionary defining the settings that this plugin expects to recieve
        through the settings parameter in the accept, validate, publish and
        finalize methods.

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
        raise NotImplementedError

    @property
    def plugin(self):
        """
        A reference to the parent Plugin class that instantiated this hook.
        """
        return self.__plugin
