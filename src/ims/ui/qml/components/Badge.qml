import QtQuick

// Small count bubble, e.g. alerts waiting.
Rectangle {
    id: root

    property int count: 0
    property string kind: "accent"  // accent | danger

    visible: count > 0
    implicitWidth: Math.max(18, label.implicitWidth + 10)
    implicitHeight: 18
    radius: 9
    color: kind === "danger" ? Theme.colors.dangerSolid : Theme.colors.accent
    scale: visible ? 1 : 0.5
    Behavior on scale { NumberAnimation { duration: Theme.motion.micro; easing.type: Easing.OutBack } }

    Txt {
        id: label
        anchors.centerIn: parent
        text: root.count > 99 ? "99+" : root.count
        variant: "caption"
        font.pixelSize: 11
        font.weight: Theme.type.semibold
        color: root.kind === "danger" ? Theme.colors.dangerOnSolid : Theme.colors.onAccent
    }
}
