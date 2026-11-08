import QtQuick

// Shows a one-time secret (a temporary password) with a Copy button.
Rectangle {
    id: root

    property string value: ""
    property bool copied: false

    width: parent ? parent.width : 320
    height: 56
    radius: Theme.radius.md
    color: Theme.colors.element
    border.width: 1
    border.color: Theme.colors.border

    TextEdit { id: clipboard; visible: false; text: root.value }

    Txt {
        anchors.left: parent.left
        anchors.leftMargin: Theme.space.md
        anchors.verticalCenter: parent.verticalCenter
        text: root.value
        font.family: "Consolas"
        font.pixelSize: 20
        font.letterSpacing: 1.5
        font.weight: Theme.type.semibold
    }

    AppButton {
        anchors.right: parent.right
        anchors.rightMargin: Theme.space.sm
        anchors.verticalCenter: parent.verticalCenter
        compact: true
        iconName: root.copied ? "check" : "copy"
        text: root.copied ? qsTr("Copied") : qsTr("Copy")
        onClicked: {
            clipboard.selectAll()
            clipboard.copy()
            root.copied = true
        }
    }
}
