import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Kits: sets of equipment deployed together, checked against their templates.
Item {
    id: view

    readonly property var columns: [0.16, 0.28, 0.18, 0.18, 0.08, 0.12]

    Component.onCompleted: Kits.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm
        Txt {
            anchors.verticalCenter: parent.verticalCenter
            width: toolbar.width - (newKit.visible ? newKit.width + Theme.space.sm : 0)
            text: qsTr("Build kits from the Drone kit and DGPS set templates; the app shows what is missing.")
            muted: true
            variant: "caption"
        }
        AppButton {
            id: newKit
            visible: Kits.canManage
            variant: "primary"
            iconName: "plus"
            text: qsTr("New kit")
            onClicked: kitSheet.openNew()
        }
    }

    Card {
        x: Theme.space.xl
        anchors.top: toolbar.bottom
        anchors.topMargin: Theme.space.md
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        elevation: "low"
        radius: Theme.radius.md

        Row {
            id: headings
            x: Theme.space.md
            width: parent.width - Theme.space.md * 2
            height: 38
            Repeater {
                model: [qsTr("Kit"), qsTr("Name"), qsTr("Template"), qsTr("Home site"), qsTr("Items"), qsTr("Status")]
                delegate: Txt {
                    required property string modelData
                    required property int index
                    width: headings.width * view.columns[index]
                    height: 38
                    text: modelData
                    variant: "caption"
                    font.weight: Theme.type.semibold
                    muted: true
                }
            }
        }
        Rectangle { y: 38; width: parent.width; height: 1; color: Theme.colors.divider }

        ListView {
            id: list
            anchors.fill: parent
            anchors.topMargin: 39
            clip: true
            model: Kits.model
            boundsBehavior: Flickable.StopAtBounds

            delegate: AbstractButton {
                id: row
                required property var model
                width: list.width
                height: 50
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                leftPadding: Theme.space.md
                rightPadding: Theme.space.md
                Accessible.name: model.code
                onClicked: kitSheet.show(model.kitId)

                background: Rectangle {
                    color: row.hovered ? Theme.colors.element : "transparent"
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                    FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                }
                contentItem: Row {
                    width: row.availableWidth
                    readonly property real w: width
                    Txt { width: parent.w * view.columns[0]; height: row.height; text: row.model.code; variant: "bodyStrong" }
                    Txt { width: parent.w * view.columns[1]; height: row.height; text: row.model.name; elide: Text.ElideRight }
                    Txt { width: parent.w * view.columns[2]; height: row.height; text: row.model.templateName || "—"; muted: !row.model.templateName }
                    Txt { width: parent.w * view.columns[3]; height: row.height; text: row.model.site || "—"; muted: !row.model.site; elide: Text.ElideRight }
                    Txt { width: parent.w * view.columns[4]; height: row.height; text: row.model.memberCount; font.features: { "tnum": 1 } }
                    Item {
                        width: parent.w * view.columns[5]
                        height: row.height
                        StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: row.model.statusKind; text: row.model.statusLabel }
                    }
                }
            }
        }

        EmptyState {
            visible: Kits.count === 0
            anchors.centerIn: parent
            iconName: "box"
            title: qsTr("No kits yet")
            message: qsTr("Group a drone with its batteries and accessories, or a base and rover with their tripods, so they go out together.")
            actionText: Kits.canManage ? qsTr("New kit") : ""
            onAction: kitSheet.openNew()
        }
    }

    KitSheet { id: kitSheet }
}
