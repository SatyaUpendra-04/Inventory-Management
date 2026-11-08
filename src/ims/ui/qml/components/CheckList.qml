import QtQuick
import QtQuick.Controls.Basic

// Multi-select list. ``model`` is an array of { value, label, detail?, kind?, status? };
// ``selected`` is the array of chosen values. Scrolls inside ``maxHeight``.
Rectangle {
    id: root

    property var model: []
    property var selected: []
    property real maxHeight: 220
    property string emptyText: qsTr("Nothing to choose from.")
    signal toggled()

    function isSelected(value) { return selected.indexOf(value) >= 0 }
    function toggle(value) {
        var next = selected.slice()
        var at = next.indexOf(value)
        if (at >= 0) next.splice(at, 1); else next.push(value)
        selected = next
        toggled()
    }
    function clear() { selected = []; toggled() }

    implicitHeight: Math.min(maxHeight, Math.max(40, list.contentHeight + 2))
    radius: Theme.radius.sm
    color: Theme.colors.surface
    border.width: 1
    border.color: Theme.colors.controlBorder

    ListView {
        id: list
        anchors.fill: parent
        anchors.margins: 1
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: root.model
        ScrollBar.vertical: ScrollBar {}
        delegate: AbstractButton {
            id: option
            required property var modelData
            required property int index
            width: list.width
            height: 36
            hoverEnabled: true
            focusPolicy: Qt.StrongFocus
            Accessible.role: Accessible.CheckBox
            Accessible.name: modelData.label
            Accessible.checked: root.isSelected(modelData.value)
            onClicked: root.toggle(modelData.value)
            Keys.onSpacePressed: root.toggle(modelData.value)

            background: Rectangle {
                color: option.hovered ? Theme.colors.element : "transparent"
                FocusRing { show: option.visualFocus; anchors.margins: 2; baseRadius: 4 }
            }
            contentItem: Item {
                Rectangle {
                    id: box
                    x: Theme.space.sm
                    anchors.verticalCenter: parent.verticalCenter
                    width: 18; height: 18; radius: 5
                    readonly property bool on: root.isSelected(option.modelData.value)
                    color: on ? Theme.colors.accent : Theme.colors.surface
                    border.width: on ? 0 : 1
                    border.color: option.hovered ? Theme.colors.textMuted : Theme.colors.controlBorder
                    Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
                    Icon { anchors.centerIn: parent; name: "check"; size: 13; color: Theme.colors.onAccent; visible: box.on }
                }
                Txt {
                    id: label
                    x: box.x + box.width + Theme.space.sm
                    anchors.verticalCenter: parent.verticalCenter
                    width: option.modelData.detail ? Math.min(implicitWidth, 160)
                           : Math.min(implicitWidth, parent.width - x - (pill.visible ? pill.width + Theme.space.md : Theme.space.sm))
                    text: option.modelData.label
                    variant: "bodyStrong"
                    elide: Text.ElideRight
                }
                Txt {
                    x: label.x + label.width + Theme.space.sm
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.max(0, parent.width - x - (pill.visible ? pill.width + Theme.space.md : Theme.space.sm))
                    text: option.modelData.detail || ""
                    muted: true
                    elide: Text.ElideRight
                }
                StatusPill {
                    id: pill
                    visible: !!option.modelData.status
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.space.sm
                    anchors.verticalCenter: parent.verticalCenter
                    kind: option.modelData.kind || "neutral"
                    text: option.modelData.status || ""
                }
            }
        }
    }
    Txt {
        visible: list.count === 0
        anchors.centerIn: parent
        text: root.emptyText
        muted: true
        variant: "caption"
    }
}
