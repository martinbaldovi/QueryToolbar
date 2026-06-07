# -*- coding: utf-8 -*-
"""
QueryToolbar – Manifold‑style query toolbar for QGIS 4.0 (Qt6)
Auto‑updates field list when fields are added or deleted.
"""

import os
from qgis.PyQt.QtCore import Qt, QDate, QMetaType
from qgis.PyQt.QtWidgets import (
    QToolBar, QComboBox, QLineEdit, QPushButton, QWidget, QHBoxLayout,
    QSpinBox, QDoubleSpinBox, QDateEdit, QCheckBox, QToolButton, QMenu
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsExpression, QgsMessageLog,
    QgsField, Qgis
)
from qgis.utils import iface


class QueryToolbar:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.toolbar = None
        self.layer = None

        self.fieldCombo = None
        self.operatorCombo = None
        self.valueContainer = None
        self.valueLayout = None
        self.valueWidget = None
        self.nullCheck = None
        self.uniqueButton = None
        self.uniqueMenu = None
        self.notButton = None
        self.selectButton = None
        self.clearButton = None

        self.uniqueCache = {}

    def initGui(self):
        # Remove existing toolbar with same name (avoid duplicates)
        existing = self.iface.mainWindow().findChild(QToolBar, "QueryToolbar")
        if existing:
            existing.deleteLater()

        self.toolbar = QToolBar("Query Toolbar")
        self.toolbar.setObjectName("QueryToolbar")
        self.toolbar.setWindowTitle("Query Toolbar")

        # Field selector
        self.fieldCombo = QComboBox()
        self.fieldCombo.setMinimumWidth(150)
        self.fieldCombo.setToolTip("Choose a field")
        self.fieldCombo.currentIndexChanged.connect(self.onFieldChanged)
        self.toolbar.addWidget(self.fieldCombo)

        # Operator selector
        self.operatorCombo = QComboBox()
        self.operatorCombo.setMinimumWidth(100)
        self.operatorCombo.setToolTip("Comparison operator")
        self.toolbar.addWidget(self.operatorCombo)

        # Dynamic value widget container
        self.valueContainer = QWidget()
        self.valueLayout = QHBoxLayout(self.valueContainer)
        self.valueLayout.setContentsMargins(0, 0, 0, 0)
        self.toolbar.addWidget(self.valueContainer)

        # NULL checkbox
        self.nullCheck = QCheckBox("NULL")
        self.nullCheck.setToolTip("Treat value as SQL NULL")
        self.nullCheck.stateChanged.connect(self.onNullChanged)
        self.toolbar.addWidget(self.nullCheck)

        # Unique values button
        self.uniqueButton = QToolButton()
        self.uniqueButton.setText("▼")
        self.uniqueButton.setToolTip("Load unique values from field")
        self.uniqueButton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.uniqueMenu = QMenu()
        self.uniqueButton.setMenu(self.uniqueMenu)
        self.uniqueMenu.aboutToShow.connect(self.loadUniqueValues)
        self.toolbar.addWidget(self.uniqueButton)

        # NOT button
        self.notButton = QPushButton("Not")
        self.notButton.setCheckable(True)
        self.notButton.setToolTip("Negate the condition")
        self.toolbar.addWidget(self.notButton)

        # Action buttons
        self.selectButton = QPushButton("Select")
        self.selectButton.clicked.connect(self.runQuery)
        self.toolbar.addWidget(self.selectButton)

        self.clearButton = QPushButton("Clear")
        self.clearButton.clicked.connect(self.clearSelection)
        self.toolbar.addWidget(self.clearButton)

        self.iface.mainWindow().addToolBar(self.toolbar)
        self.toolbar.setVisible(True)

        # Signals for project and layer changes
        QgsProject.instance().layersAdded.connect(self.onLayersChanged)
        QgsProject.instance().layersRemoved.connect(self.onLayersChanged)
        self.iface.mapCanvas().currentLayerChanged.connect(self.onCurrentLayerChanged)

        self.onLayersChanged()

    def unload(self):
        # Disconnect from current layer's field‑changed signal
        if self.layer:
            try:
                self.layer.updatedFields.disconnect(self.onLayerFieldsChanged)
            except TypeError:
                pass
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None

    # ----------------------------------------------------------------------
    # Layer & field management
    # ----------------------------------------------------------------------
    def onLayersChanged(self):
        self.onCurrentLayerChanged(self.iface.mapCanvas().currentLayer())

    def onCurrentLayerChanged(self, layer):
        # Disconnect from previous layer's field‑changed signal
        if self.layer:
            try:
                self.layer.updatedFields.disconnect(self.onLayerFieldsChanged)
            except TypeError:
                pass
            self.uniqueCache.clear()

        self.layer = layer if isinstance(layer, QgsVectorLayer) else None

        if self.layer:
            # Connect to signal that fires when fields are added/deleted
            self.layer.updatedFields.connect(self.onLayerFieldsChanged)

        self.updateFieldList()
        self.updateOperatorList()
        self.updateValueWidget()

    def onLayerFieldsChanged(self):
        """Slot called when the layer's fields are modified (added/deleted)."""
        if self.layer is self.iface.mapCanvas().currentLayer():
            self.uniqueCache.clear()
            self.updateFieldList()
            self.updateOperatorList()
            self.updateValueWidget()

    def updateFieldList(self):
        self.fieldCombo.clear()
        if not self.layer:
            return
        for field in self.layer.fields():
            self.fieldCombo.addItem(field.name(), field.name())

    def onFieldChanged(self, index):
        if index < 0:
            return
        self.updateOperatorList()
        self.updateValueWidget()
        field_name = self.fieldCombo.currentData()
        if field_name:
            self.uniqueCache.pop(field_name, None)

    # ----------------------------------------------------------------------
    # Field type classification (using QMetaType)
    # ----------------------------------------------------------------------
    def _is_numeric(self, field_type):
        numeric_types = (
            QMetaType.Type.Int, QMetaType.Type.UInt,
            QMetaType.Type.LongLong, QMetaType.Type.ULongLong,
            QMetaType.Type.Short, QMetaType.Type.UShort,
            QMetaType.Type.Char, QMetaType.Type.SChar, QMetaType.Type.UChar,
            QMetaType.Type.Double, QMetaType.Type.Float,
        )
        return field_type in numeric_types

    def _is_integer(self, field_type):
        integer_types = (
            QMetaType.Type.Int, QMetaType.Type.UInt,
            QMetaType.Type.LongLong, QMetaType.Type.ULongLong,
            QMetaType.Type.Short, QMetaType.Type.UShort,
            QMetaType.Type.Char, QMetaType.Type.SChar, QMetaType.Type.UChar,
        )
        return field_type in integer_types

    def _is_date_or_time(self, field_type):
        date_types = (
            QMetaType.Type.QDate,
            QMetaType.Type.QTime,
            QMetaType.Type.QDateTime,
        )
        return field_type in date_types

    # ----------------------------------------------------------------------
    # Operator list (type‑aware)
    # ----------------------------------------------------------------------
    def updateOperatorList(self):
        self.operatorCombo.clear()
        if not self.layer:
            return
        field_name = self.fieldCombo.currentData()
        if not field_name:
            return
        field = self.layer.fields().field(field_name)
        field_type = field.type()
        basic_ops = ["=", "<>", "<", "<=", ">", ">="]

        if self._is_numeric(field_type):
            ops = basic_ops
        elif self._is_date_or_time(field_type):
            ops = basic_ops + ["Is before", "Is after"]
        else:
            ops = basic_ops + ["Contains", "Does not contain", "Begins with", "Ends with", "Like"]

        for op in ops:
            self.operatorCombo.addItem(op, op)

    # ----------------------------------------------------------------------
    # Dynamic value widget – no forced width on any widget
    # ----------------------------------------------------------------------
    def updateValueWidget(self):
        # Remove old widget
        while self.valueLayout.count():
            child = self.valueLayout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not self.layer or not self.fieldCombo.currentData():
            self.valueWidget = QLineEdit()
            self.valueWidget.setPlaceholderText("Enter value...")
            self.valueLayout.addWidget(self.valueWidget)
            return

        field_name = self.fieldCombo.currentData()
        field = self.layer.fields().field(field_name)
        field_type = field.type()

        if self._is_numeric(field_type):
            if self._is_integer(field_type):
                spin = QSpinBox()
                spin.setMinimum(-2147483647)
                spin.setMaximum(2147483647)
                spin.setSpecialValueText("")
                spin.setToolTip("Enter an integer value")
                self.valueWidget = spin
            else:
                dspin = QDoubleSpinBox()
                dspin.setMinimum(-1e9)
                dspin.setMaximum(1e9)
                dspin.setDecimals(6)
                dspin.setSpecialValueText("")
                dspin.setToolTip("Enter a decimal number")
                self.valueWidget = dspin
        elif self._is_date_or_time(field_type):
            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setSpecialValueText("")
            date_edit.setDate(QDate.currentDate())
            date_edit.setToolTip("Pick a date")
            self.valueWidget = date_edit
        else:
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("Enter value...")
            line_edit.setToolTip("String value")
            self.valueWidget = line_edit

        self.valueLayout.addWidget(self.valueWidget)
        self.nullCheck.setChecked(False)
        self.valueWidget.setEnabled(True)

    # ----------------------------------------------------------------------
    # Unique values (on‑demand)
    # ----------------------------------------------------------------------
    def loadUniqueValues(self):
        self.uniqueMenu.clear()
        if not self.layer or not self.fieldCombo.currentData():
            self.uniqueButton.setEnabled(False)
            return
        field_name = self.fieldCombo.currentData()
        if field_name in self.uniqueCache:
            values = self.uniqueCache[field_name]
        else:
            idx = self.layer.fields().indexFromName(field_name)
            values = self.layer.uniqueValues(idx, limit=1000)
            self.uniqueCache[field_name] = values
        if not values:
            self.uniqueButton.setEnabled(False)
            return
        self.uniqueButton.setEnabled(True)
        for v in values:
            if v is None or (hasattr(v, 'isNull') and v.isNull()):
                display = "(NULL)"
            else:
                display = str(v)
            action = self.uniqueMenu.addAction(display)
            action.setData(v)
            action.triggered.connect(lambda checked, val=v: self.setValueFromUnique(val))

    def setValueFromUnique(self, value):
        if value is None or (hasattr(value, 'isNull') and value.isNull()):
            self.nullCheck.setChecked(True)
        else:
            self.nullCheck.setChecked(False)
            if isinstance(self.valueWidget, QSpinBox):
                self.valueWidget.setValue(int(value))
            elif isinstance(self.valueWidget, QDoubleSpinBox):
                self.valueWidget.setValue(float(value))
            elif isinstance(self.valueWidget, QDateEdit):
                if hasattr(value, 'toDate'):
                    d = value.toDate()
                elif isinstance(value, QDate):
                    d = value
                else:
                    d = QDate.fromString(str(value), Qt.DateFormat.ISODate)
                if d.isValid():
                    self.valueWidget.setDate(d)
            else:
                self.valueWidget.setText(str(value))

    # ----------------------------------------------------------------------
    # NULL handling
    # ----------------------------------------------------------------------
    def onNullChanged(self, state):
        is_null = (state == Qt.CheckState.Checked.value)
        self.valueWidget.setEnabled(not is_null)
        self.uniqueButton.setEnabled(not is_null)

    def getCurrentValue(self):
        if self.nullCheck.isChecked():
            return None
        if isinstance(self.valueWidget, QSpinBox):
            return self.valueWidget.value()
        elif isinstance(self.valueWidget, QDoubleSpinBox):
            return self.valueWidget.value()
        elif isinstance(self.valueWidget, QDateEdit):
            return self.valueWidget.date().toString("yyyy-MM-dd")
        else:
            return self.valueWidget.text()

    # ----------------------------------------------------------------------
    # Query execution
    # ----------------------------------------------------------------------
    def buildExpression(self, field_name, operator, value, negate):
        if value is None:
            expr = f'"{field_name}" IS NULL'
            if negate:
                expr = f'"{field_name}" IS NOT NULL'
            return expr, True, ""
        if isinstance(value, str):
            value_escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            value_repr = f"'{value_escaped}'"
        else:
            value_repr = str(value)
        op_lower = operator.lower()
        if op_lower == "contains":
            expr = f'"{field_name}" LIKE \'%{value_escaped}%\''
        elif op_lower == "does not contain":
            expr = f'"{field_name}" NOT LIKE \'%{value_escaped}%\''
        elif op_lower == "begins with":
            expr = f'"{field_name}" LIKE \'{value_escaped}%\''
        elif op_lower == "ends with":
            expr = f'"{field_name}" LIKE \'%{value_escaped}\''
        elif op_lower == "like":
            expr = f'"{field_name}" LIKE {value_repr}'
        elif op_lower == "is before":
            expr = f'"{field_name}" < {value_repr}'
        elif op_lower == "is after":
            expr = f'"{field_name}" > {value_repr}'
        else:
            expr = f'"{field_name}" {operator} {value_repr}'
        if negate:
            expr = f"NOT ({expr})"
        exp = QgsExpression(expr)
        if exp.hasParserError():
            return expr, False, exp.parserErrorString()
        return expr, True, ""

    def runQuery(self):
        if not self.layer or not isinstance(self.layer, QgsVectorLayer):
            self.iface.messageBar().pushMessage(
                "QueryToolbar", "No vector layer selected", level=Qgis.Warning, duration=3
            )
            return
        field_name = self.fieldCombo.currentData()
        operator = self.operatorCombo.currentText()
        value = self.getCurrentValue()
        negate = self.notButton.isChecked()
        if not field_name or not operator:
            return
        expr_str, valid, err_msg = self.buildExpression(field_name, operator, value, negate)
        if not valid:
            self.iface.messageBar().pushMessage(
                "Expression Error", err_msg, level=Qgis.Critical, duration=5
            )
            QgsMessageLog.logMessage(f"QueryToolbar expression error: {err_msg}", "QueryToolbar", Qgis.Critical)
            return
        try:
            self.layer.selectByExpression(expr_str, QgsVectorLayer.SetSelection)
            count = self.layer.selectedFeatureCount()
            self.iface.messageBar().pushMessage(
                "QueryToolbar", f"Selected {count} feature(s)", level=Qgis.Info, duration=2
            )
            QgsMessageLog.logMessage(f"Selected {count} features with expression: {expr_str}", "QueryToolbar", Qgis.Info)
        except Exception as e:
            self.iface.messageBar().pushMessage(
                "Query Error", str(e), level=Qgis.Critical, duration=5
            )
            QgsMessageLog.logMessage(f"QueryToolbar runtime error: {e}", "QueryToolbar", Qgis.Critical)

    def clearSelection(self):
        if self.layer:
            self.layer.removeSelection()
            self.iface.messageBar().pushMessage("QueryToolbar", "Selection cleared", level=Qgis.Info, duration=2)
