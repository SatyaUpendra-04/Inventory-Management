import QtQuick
import QtQuick.Effects

// Full-window frame for the screens before the app: setup, sign-in, password, profile.
Rectangle {
    id: root

    property string title: ""
    property string subtitle: ""
    property int cardWidth: 400
    property alias footer: footerSlot.data
    default property alias content: form.data

    color: Theme.colors.window

    Rectangle {
        width: 760
        height: 760
        radius: 380
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -80
        color: Theme.colors.accent
        opacity: Theme.dark ? 0.16 : 0.10
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
    }

    Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: Math.max(height, card.height + Theme.space.xxl * 2)
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Card {
            id: card
            width: root.cardWidth
            height: column.implicitHeight + Theme.space.xl * 2
            anchors.centerIn: parent
            elevation: "high"
            radius: Theme.radius.lg + 4
            fill: Theme.colors.surfaceRaised
            padding: Theme.space.xl

            Column {
                id: column
                width: parent.width
                spacing: Theme.space.md

                Rectangle {
                    width: 52
                    height: 52
                    radius: 14
                    color: Theme.colors.accent
                    anchors.horizontalCenter: parent.horizontalCenter
                    Icon { anchors.centerIn: parent; name: "drone"; size: 28; color: Theme.colors.onAccent }
                }
                Column {
                    width: parent.width
                    spacing: 2
                    Txt {
                        width: parent.width
                        text: root.title
                        variant: "title2"
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                    Txt {
                        width: parent.width
                        visible: root.subtitle !== ""
                        text: root.subtitle
                        muted: true
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }
                }
                Item { width: 1; height: 2 }
                Column {
                    id: form
                    width: parent.width
                    spacing: Theme.space.md
                }
                Item {
                    id: footerSlot
                    width: parent.width
                    implicitHeight: childrenRect.height
                    height: implicitHeight
                }
            }
        }
    }
}
