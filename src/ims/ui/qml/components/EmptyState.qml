import QtQuick

// Friendly placeholder when there is nothing to show yet.
Column {
    id: root

    property string iconName: "inbox"
    property string title: ""
    property string message: ""
    property string actionText: ""

    signal action()

    width: 420
    spacing: Theme.space.sm

    Rectangle {
        width: 56
        height: 56
        radius: Theme.radius.lg
        color: Theme.colors.accentSubtle
        anchors.horizontalCenter: parent.horizontalCenter
        Icon {
            anchors.centerIn: parent
            name: root.iconName
            size: 26
            color: Theme.colors.accentText
        }
    }
    Item { width: 1; height: 4 }
    Txt {
        width: parent.width
        text: root.title
        variant: "headline"
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
    }
    Txt {
        width: parent.width
        text: root.message
        muted: true
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        lineHeight: 1.3
    }
    Item { width: 1; height: 4; visible: root.actionText !== "" }
    AppButton {
        visible: root.actionText !== ""
        text: root.actionText
        variant: "primary"
        anchors.horizontalCenter: parent.horizontalCenter
        onClicked: root.action()
    }
}
