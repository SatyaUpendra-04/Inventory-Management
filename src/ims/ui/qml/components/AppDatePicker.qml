import QtQuick
import QtQuick.Controls.Basic

// Date field that opens a calendar. The calendar's title switches between a month of
// days, the twelve months of a year and twelve years at a time, so far-off dates
// (a licence expiry, an acquisition date) take a few clicks, not dozens.
Column {
    id: root

    property string label: ""
    property date selectedDate: new Date()
    property bool hasDate: false
    property string placeholder: qsTr("Choose a date")

    signal picked(date value)

    width: 220
    spacing: 6

    Txt {
        visible: root.label !== ""
        text: root.label
        variant: "caption"
        font.weight: Theme.type.medium
    }

    AbstractButton {
        id: field
        width: parent.width
        height: 34
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: root.label || root.placeholder
        onClicked: calendar.open()

        contentItem: Item {
            Txt {
                anchors.left: parent.left
                anchors.leftMargin: Theme.space.sm
                anchors.verticalCenter: parent.verticalCenter
                text: root.hasDate ? root.selectedDate.toLocaleDateString(Qt.locale(), "d MMM yyyy")
                                   : root.placeholder
                muted: !root.hasDate
            }
            Icon {
                anchors.right: parent.right
                anchors.rightMargin: Theme.space.sm
                anchors.verticalCenter: parent.verticalCenter
                name: "calendar"
                size: 16
                color: Theme.colors.textMuted
            }
        }
        background: Rectangle {
            radius: Theme.radius.sm
            color: Theme.colors.surface
            border.width: 1
            border.color: field.hovered ? Theme.colors.textMuted : Theme.colors.controlBorder
            FocusRing { show: field.visualFocus || calendar.visible }
        }
    }

    Popup {
        id: calendar
        objectName: "calendar"

        // days: a month of days · months: the 12 months of a year · years: 12 years at a time
        property string mode: "days"
        property int month: root.selectedDate.getMonth()
        property int year: root.selectedDate.getFullYear()
        readonly property int firstYear: year - (((year % 12) + 12) % 12)

        function step(direction) {
            if (mode === "days") {
                var m = month + direction
                year += Math.floor(m / 12)
                month = ((m % 12) + 12) % 12
            } else if (mode === "months") {
                year += direction
            } else {
                year += direction * 12
            }
        }
        function choose(value) {
            root.selectedDate = value
            root.hasDate = true
            root.picked(value)
            calendar.close()
        }

        y: field.y + field.height + 4
        width: 280
        padding: Theme.space.sm
        transformOrigin: Item.Top
        onAboutToShow: {
            var start = root.hasDate ? root.selectedDate : new Date()
            month = start.getMonth(); year = start.getFullYear(); mode = "days"
        }

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.micro }
            NumberAnimation { property: "scale"; from: Theme.reducedMotion ? 1 : 0.96; to: 1
                              duration: Theme.motion.standard; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: Theme.motion.micro } }

        background: Card { elevation: "medium"; radius: Theme.radius.md; fill: Theme.colors.surfaceRaised }

        contentItem: Column {
            spacing: Theme.space.xs

            // Page Up / Page Down step back and forward; with Shift, a year (or 12 years) at a time.
            Keys.onPressed: function (event) {
                var big = (event.modifiers & Qt.ShiftModifier) && calendar.mode === "days" ? 12 : 1
                if (event.key === Qt.Key_PageUp) { calendar.step(-big); event.accepted = true }
                else if (event.key === Qt.Key_PageDown) { calendar.step(big); event.accepted = true }
            }

            Item {
                width: parent.width
                height: 32
                IconButton {
                    objectName: "previous"
                    anchors.left: parent.left
                    iconName: "chevron-left"
                    tip: calendar.mode === "days" ? qsTr("Previous month")
                         : calendar.mode === "months" ? qsTr("Previous year") : qsTr("Previous 12 years")
                    onClicked: calendar.step(-1)
                }
                // The title is a button: days, then months, then years, as in the system calendars.
                AbstractButton {
                    id: title
                    objectName: "calendarTitle"
                    anchors.centerIn: parent
                    height: 30
                    width: titleRow.implicitWidth + Theme.space.md
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    enabled: calendar.mode !== "years"
                    Accessible.name: titleText.text
                    onClicked: calendar.mode = calendar.mode === "days" ? "months" : "years"
                    background: Rectangle {
                        radius: Theme.radius.sm
                        color: title.hovered && title.enabled ? Theme.colors.element : "transparent"
                        FocusRing { show: title.visualFocus }
                    }
                    contentItem: Item {
                        Row {
                            id: titleRow
                            anchors.centerIn: parent
                            spacing: 4
                            Txt {
                                id: titleText
                                objectName: "calendarTitleText"
                                variant: "bodyStrong"
                                text: calendar.mode === "days"
                                      ? new Date(calendar.year, calendar.month, 1).toLocaleDateString(Qt.locale(), "MMMM yyyy")
                                      : calendar.mode === "months" ? String(calendar.year)
                                      : calendar.firstYear + " – " + (calendar.firstYear + 11)
                            }
                            Icon {
                                visible: title.enabled
                                anchors.verticalCenter: parent.verticalCenter
                                name: "chevron-down"
                                size: 14
                                color: Theme.colors.textMuted
                            }
                        }
                    }
                }
                IconButton {
                    objectName: "next"
                    anchors.right: parent.right
                    iconName: "chevron-right"
                    tip: calendar.mode === "days" ? qsTr("Next month")
                         : calendar.mode === "months" ? qsTr("Next year") : qsTr("Next 12 years")
                    onClicked: calendar.step(1)
                }
            }

            // ------------------------------------------------------------ days
            DayOfWeekRow {
                id: weekdays
                visible: calendar.mode === "days"
                width: parent.width
                locale: Qt.locale()
                delegate: Txt {
                    required property string shortName
                    text: shortName
                    variant: "caption"
                    muted: true
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            MonthGrid {
                id: grid
                visible: calendar.mode === "days"
                width: parent.width
                month: calendar.month
                year: calendar.year
                locale: Qt.locale()

                delegate: AbstractButton {
                    id: day
                    required property var model
                    readonly property bool isSelected: root.hasDate
                        && model.date.getFullYear() === root.selectedDate.getFullYear()
                        && model.date.getMonth() === root.selectedDate.getMonth()
                        && model.date.getDate() === root.selectedDate.getDate()

                    implicitWidth: 34
                    implicitHeight: 32
                    hoverEnabled: true
                    focusPolicy: Qt.NoFocus
                    onClicked: calendar.choose(model.date)

                    contentItem: Txt {
                        text: day.model.day
                        horizontalAlignment: Text.AlignHCenter
                        variant: day.isSelected ? "bodyStrong" : "body"
                        color: day.isSelected ? Theme.colors.onAccent
                             : day.model.today ? Theme.colors.accentText
                             : day.model.month === grid.month ? Theme.colors.text : Theme.colors.textMuted
                        opacity: day.model.month === grid.month || day.isSelected ? 1 : 0.6
                    }
                    background: Rectangle {
                        anchors.centerIn: parent
                        width: 30
                        height: 30
                        radius: 15
                        color: day.isSelected ? Theme.colors.accent
                             : day.hovered ? Theme.colors.element : "transparent"
                        border.width: day.model.today && !day.isSelected ? 1 : 0
                        border.color: Theme.colors.accentBorder
                    }
                }
            }

            // ------------------------------------------------------------ months and years
            Grid {
                id: picker
                objectName: "monthYearGrid"
                visible: calendar.mode !== "days"
                width: parent.width
                columns: 3
                rowSpacing: Theme.space.xs
                columnSpacing: Theme.space.xs
                // As tall as the weekday row plus the day grid, so the popup never jumps.
                readonly property real cellHeight:
                    (weekdays.implicitHeight + grid.implicitHeight + Theme.space.xs - rowSpacing * 3) / 4

                Repeater {
                    model: 12
                    delegate: AbstractButton {
                        id: cell
                        required property int index
                        readonly property bool months: calendar.mode === "months"
                        readonly property int value: months ? index : calendar.firstYear + index
                        readonly property bool isSelected: root.hasDate && (months
                            ? root.selectedDate.getFullYear() === calendar.year && root.selectedDate.getMonth() === index
                            : root.selectedDate.getFullYear() === value)
                        readonly property bool isNow: months
                            ? new Date().getFullYear() === calendar.year && new Date().getMonth() === index
                            : new Date().getFullYear() === value

                        objectName: "cell" + index
                        width: (picker.width - picker.columnSpacing * 2) / 3
                        height: picker.cellHeight
                        hoverEnabled: true
                        focusPolicy: Qt.NoFocus
                        Accessible.name: label.text
                        onClicked: {
                            if (months) { calendar.month = index; calendar.mode = "days" }
                            else { calendar.year = value; calendar.mode = "months" }
                        }
                        contentItem: Txt {
                            id: label
                            text: cell.months ? new Date(2000, cell.index, 1).toLocaleDateString(Qt.locale(), "MMM")
                                              : String(cell.value)
                            horizontalAlignment: Text.AlignHCenter
                            variant: cell.isSelected ? "bodyStrong" : "body"
                            color: cell.isSelected ? Theme.colors.onAccent
                                 : cell.isNow ? Theme.colors.accentText : Theme.colors.text
                        }
                        background: Rectangle {
                            anchors.centerIn: parent
                            width: parent.width - 4
                            height: 34
                            radius: 17
                            color: cell.isSelected ? Theme.colors.accent
                                 : cell.hovered ? Theme.colors.element : "transparent"
                            border.width: cell.isNow && !cell.isSelected ? 1 : 0
                            border.color: Theme.colors.accentBorder
                            Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
                        }
                    }
                }
            }

            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Item {
                width: parent.width
                height: 28
                AppButton {
                    objectName: "today"
                    anchors.left: parent.left
                    compact: true
                    variant: "ghost"
                    text: qsTr("Today")
                    onClicked: calendar.choose(new Date())
                }
                AppButton {
                    objectName: "clear"
                    visible: root.hasDate
                    anchors.right: parent.right
                    compact: true
                    variant: "ghost"
                    text: qsTr("Clear")
                    onClicked: { root.hasDate = false; calendar.close() }
                }
            }
        }
    }
}
