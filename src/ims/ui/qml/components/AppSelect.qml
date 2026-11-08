import QtQuick
import QtQuick.Controls.Basic

// Drop-down list. ``model`` is an array of strings, or of objects with ``textRole`` and
// ``valueRole`` (e.g. [{ value: "pilot", label: "Pilot" }]); read ``currentValue``.
ComboBox {
    id: control

    function selectValue(value) {
        var index = indexOfValue(value)
        currentIndex = index >= 0 ? index : 0
    }

    implicitWidth: 220
    implicitHeight: 34
    hoverEnabled: true
    font.family: Theme.type.family
    font.pixelSize: Theme.type.body
    leftPadding: Theme.space.sm
    rightPadding: 34

    delegate: ItemDelegate {
        id: option
        required property var modelData
        required property int index

        width: ListView.view ? ListView.view.width : control.width
        height: 32
        hoverEnabled: true
        highlighted: control.highlightedIndex === index

        contentItem: Row {
            spacing: Theme.space.xs
            Icon {
                name: "check"
                size: 16
                color: Theme.colors.accentText
                opacity: control.currentIndex === option.index ? 1 : 0
                anchors.verticalCenter: parent.verticalCenter
            }
            Txt {
                text: control.textRole ? option.modelData[control.textRole] : option.modelData
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        background: Rectangle {
            radius: Theme.radius.sm - 2
            color: option.highlighted ? Theme.colors.accentSubtle : "transparent"
        }
    }

    indicator: Icon {
        name: "chevron-down"
        size: 16
        color: Theme.colors.textMuted
        x: control.width - width - Theme.space.sm
        anchors.verticalCenter: parent.verticalCenter
        rotation: control.popup.visible ? 180 : 0
        Behavior on rotation { NumberAnimation { duration: Theme.motion.standard; easing.type: Easing.OutCubic } }
    }

    contentItem: Txt {
        text: control.displayText
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: Theme.radius.sm
        color: control.down ? Theme.colors.element : Theme.colors.surface
        border.width: 1
        border.color: control.hovered ? Theme.colors.textMuted : Theme.colors.controlBorder
        Behavior on border.color { ColorAnimation { duration: Theme.motion.micro } }
        FocusRing { show: control.visualFocus || control.popup.visible }
    }

    popup: Popup {
        y: control.height + 4
        width: control.width
        padding: 4
        transformOrigin: Item.Top

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.micro }
            NumberAnimation { property: "scale"; from: Theme.reducedMotion ? 1 : 0.96; to: 1
                              duration: Theme.motion.standard; easing.type: Easing.OutCubic }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: Theme.motion.micro }
        }

        contentItem: ListView {
            clip: true
            implicitHeight: Math.min(contentHeight, 280)
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }

        background: Card {
            elevation: "medium"
            radius: Theme.radius.md
            fill: Theme.colors.surfaceRaised
        }
    }
}
