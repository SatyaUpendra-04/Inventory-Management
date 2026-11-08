import QtQuick

// Round profile picture, or initials when there is no picture yet.
// The circle crop is done by the image provider, so it renders the same everywhere.
Item {
    id: root

    property string source: ""
    property string initials: ""
    property int size: 32

    width: size
    height: size

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: Theme.colors.accentSubtleHover
        visible: picture.status !== Image.Ready
        Txt {
            anchors.centerIn: parent
            text: root.initials
            font.pixelSize: Math.max(10, root.size * 0.38)
            font.weight: Theme.type.semibold
            color: Theme.colors.accentText
        }
    }

    Image {
        id: picture
        anchors.fill: parent
        source: root.source ? root.source + "?round" : ""
        sourceSize: Qt.size(Math.ceil(root.size * Screen.devicePixelRatio),
                            Math.ceil(root.size * Screen.devicePixelRatio))
        fillMode: Image.PreserveAspectFit
        smooth: true
        visible: status === Image.Ready
    }

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(0, 0, 0, Theme.dark ? 0.35 : 0.08)
        visible: picture.visible
    }
}
