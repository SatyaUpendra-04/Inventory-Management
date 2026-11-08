import QtQuick
import QtQuick.Controls.Basic

// Date field that opens a month calendar.
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

        property int month: root.selectedDate.getMonth()
        property int year: root.selectedDate.getFullYear()

        y: field.y + field.height + 4
        width: 280
        padding: Theme.space.sm
        transformOrigin: Item.Top
        onAboutToShow: { month = root.selectedDate.getMonth(); year = root.selectedDate.getFullYear() }

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.micro }
            NumberAnimation { property: "scale"; from: Theme.reducedMotion ? 1 : 0.96; to: 1
                              duration: Theme.motion.standard; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: Theme.motion.micro } }

        background: Card { elevation: "medium"; radius: Theme.radius.md; fill: Theme.colors.surfaceRaised }

        contentItem: Column {
            spacing: Theme.space.xs

            Item {
                width: parent.width
                height: 32
                IconButton {
                    anchors.left: parent.left
                    iconName: "chevron-left"
                    tip: qsTr("Previous month")
                    onClicked: {
                        if (calendar.month === 0) { calendar.month = 11; calendar.year -= 1 }
                        else calendar.month -= 1
                    }
                }
                Txt {
                    anchors.centerIn: parent
                    variant: "bodyStrong"
                    text: new Date(calendar.year, calendar.month, 1).toLocaleDateString(Qt.locale(), "MMMM yyyy")
                }
                IconButton {
                    anchors.right: parent.right
                    iconName: "chevron-right"
                    tip: qsTr("Next month")
                    onClicked: {
                        if (calendar.month === 11) { calendar.month = 0; calendar.year += 1 }
                        else calendar.month += 1
                    }
                }
            }

            DayOfWeekRow {
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
                    onClicked: {
                        root.selectedDate = model.date
                        root.hasDate = true
                        root.picked(model.date)
                        calendar.close()
                    }

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
        }
    }
}
