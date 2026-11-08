import QtQuick
import QtQuick.Controls.Basic

// Stack of notifications in the top-right corner, fed by the Toasts service.
Item {
    id: root

    property int lifetime: 4500

    width: 360
    height: list.contentHeight

    ListModel { id: toasts }

    Connections {
        target: Toasts
        function onPosted(kind, title, message) {
            toasts.insert(0, { kind: kind, title: title, message: message })
            if (toasts.count > 4) toasts.remove(toasts.count - 1)
        }
    }

    ListView {
        id: list
        anchors.fill: parent
        interactive: false
        spacing: Theme.space.xs
        model: toasts

        add: Transition {
            NumberAnimation { property: "x"; from: Theme.reducedMotion ? 0 : 60; to: 0
                              duration: Theme.motion.page; easing.type: Easing.BezierSpline
                              easing.bezierCurve: Theme.motion.easing }
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.standard }
        }
        remove: Transition {
            NumberAnimation { property: "opacity"; to: 0; duration: Theme.motion.standard }
            NumberAnimation { property: "x"; to: Theme.reducedMotion ? 0 : 40; duration: Theme.motion.standard }
        }
        displaced: Transition {
            NumberAnimation { properties: "y"; duration: Theme.motion.standard; easing.type: Easing.OutCubic }
        }

        delegate: Card {
            id: toast
            required property int index
            required property string kind
            required property string title
            required property string message

            width: root.width
            height: content.implicitHeight + Theme.space.md * 2
            elevation: "high"
            radius: Theme.radius.md
            fill: Theme.colors.surfaceRaised
            Accessible.role: Accessible.AlertMessage
            Accessible.name: title + ". " + message

            Rectangle {
                width: 3
                radius: 1.5
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.margins: Theme.space.sm
                color: Theme.colors[toast.kind + "Solid"]
            }

            Row {
                id: content
                x: Theme.space.md + 6
                y: Theme.space.md
                width: parent.width - x - 40
                spacing: Theme.space.sm

                Icon {
                    name: ({ success: "circle-check", warning: "alert", danger: "circle-x", info: "info" })[toast.kind]
                    size: 20
                    color: Theme.colors[toast.kind + "Text"]
                }
                Column {
                    width: parent.width - 32
                    spacing: 2
                    Txt { text: toast.title; variant: "bodyStrong"; width: parent.width; wrapMode: Text.WordWrap }
                    Txt {
                        visible: toast.message !== ""
                        text: toast.message
                        muted: true
                        width: parent.width
                        wrapMode: Text.WordWrap
                    }
                }
            }

            IconButton {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 6
                width: 28
                height: 28
                iconName: "x"
                iconSize: 15
                tip: qsTr("Dismiss")
                onClicked: toasts.remove(toast.index)
            }

            Timer {
                interval: root.lifetime
                running: true
                onTriggered: if (toast.index >= 0) toasts.remove(toast.index)
            }
        }
    }
}
