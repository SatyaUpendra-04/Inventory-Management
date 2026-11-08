import QtQuick
import QtQuick.Controls.Basic

// Pick one of a few options; the selection "thumb" glides between segments.
// options: [{ value: "light", label: "Light", icon: "sun" }, ...]
FocusScope {
    id: root

    property var options: []
    property string value: ""
    property int segmentWidth: 96

    signal activated(string value)

    readonly property int _index: {
        for (var i = 0; i < options.length; ++i)
            if (options[i].value === value) return i
        return -1
    }

    implicitWidth: options.length * segmentWidth + 4
    implicitHeight: 32
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList

    Keys.onLeftPressed: if (_index > 0) root.activated(options[_index - 1].value)
    Keys.onRightPressed: if (_index < options.length - 1) root.activated(options[_index + 1].value)

    Rectangle {
        anchors.fill: parent
        radius: Theme.radius.sm + 2
        color: Theme.colors.element
        border.width: 1
        border.color: Theme.colors.divider
        FocusRing { show: root.activeFocus; baseRadius: Theme.radius.sm + 2 }
    }

    Card {
        visible: root._index >= 0
        elevation: "low"
        outlined: false
        radius: Theme.radius.sm
        fill: Theme.dark ? Theme.colors.elementActive : Theme.colors.surface
        width: root.segmentWidth
        height: root.height - 4
        y: 2
        x: 2 + Math.max(0, root._index) * root.segmentWidth
        Behavior on x {
            enabled: !Theme.reducedMotion
            SpringAnimation { spring: Theme.motion.springStiffness; damping: Theme.motion.springDamping; epsilon: 0.25 }
        }
    }

    Row {
        x: 2
        y: 2
        Repeater {
            model: root.options
            delegate: AbstractButton {
                id: segment
                required property var modelData
                required property int index
                width: root.segmentWidth
                height: root.height - 4
                hoverEnabled: true
                focusPolicy: Qt.NoFocus
                Accessible.name: modelData.label
                onClicked: root.activated(modelData.value)

                contentItem: Item {
                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Icon {
                            visible: !!segment.modelData.icon
                            name: segment.modelData.icon || ""
                            size: 15
                            color: root._index === segment.index ? Theme.colors.text : Theme.colors.textMuted
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Txt {
                            text: segment.modelData.label
                            variant: "caption"
                            font.weight: root._index === segment.index ? Theme.type.semibold : Theme.type.medium
                            color: root._index === segment.index ? Theme.colors.text : Theme.colors.textMuted
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
                background: Item {}
            }
        }
    }
}
