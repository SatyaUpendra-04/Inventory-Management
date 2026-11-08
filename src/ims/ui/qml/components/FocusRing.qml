import QtQuick

// Keyboard focus indicator: drawn just outside its parent (or just inside, with ``inset``,
// where the parent sits in a clipped list), and fades in and out.
Rectangle {
    id: root

    property bool show: false
    property real baseRadius: Theme.radius.sm
    property bool inset: false

    anchors.fill: parent
    anchors.margins: inset ? 0 : -3
    radius: inset ? baseRadius : baseRadius + 3
    color: "transparent"
    border.width: 2
    border.color: Theme.colors.focusRing
    opacity: show ? 1 : 0
    visible: opacity > 0

    Behavior on opacity {
        NumberAnimation { duration: Theme.motion.micro }
    }
}
