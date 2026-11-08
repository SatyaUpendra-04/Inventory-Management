import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Sites: stores, mine sites, workshops and offices.
Item {
    id: page

    property var section: ({})
    readonly property var columns: [0.16, 0.26, 0.13, 0.17, 0.16, 0.12]

    Component.onCompleted: Sites.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm
        Txt {
            anchors.verticalCenter: parent.verticalCenter
            width: toolbar.width - (addButton.visible ? addButton.width + Theme.space.sm : 0)
            text: qsTr("%n sites", "", Sites.count)
            muted: true
            variant: "caption"
        }
        AppButton {
            id: addButton
            visible: Sites.canManage
            variant: "primary"
            iconName: "plus"
            text: qsTr("Add site")
            onClicked: siteSheet.openNew()
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
                model: [qsTr("Code"), qsTr("Name"), qsTr("Type"), qsTr("Region"), qsTr("Coordinates"), qsTr("Status")]
                delegate: Txt {
                    required property string modelData
                    required property int index
                    width: headings.width * page.columns[index]
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
            model: Sites.model
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            delegate: AbstractButton {
                id: row
                required property var model
                width: list.width
                height: 50
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                leftPadding: Theme.space.md
                rightPadding: Theme.space.md
                Accessible.name: model.code + " " + model.name
                onClicked: siteSheet.openEdit(model.siteId)

                background: Rectangle {
                    color: row.hovered ? Theme.colors.element : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                    FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                }
                contentItem: Row {
                    width: row.availableWidth
                    readonly property real w: width
                    Txt { width: parent.w * page.columns[0]; height: row.height; text: row.model.code; variant: "bodyStrong" }
                    Txt { width: parent.w * page.columns[1]; height: row.height; text: row.model.name; elide: Text.ElideRight }
                    Txt { width: parent.w * page.columns[2]; height: row.height; text: row.model.kindLabel }
                    Txt { width: parent.w * page.columns[3]; height: row.height; text: row.model.region || "—"; muted: !row.model.region; elide: Text.ElideRight }
                    Txt { width: parent.w * page.columns[4]; height: row.height; text: row.model.coordinates || "—"; muted: true; font.features: { "tnum": 1 } }
                    Item {
                        width: parent.w * page.columns[5]
                        height: row.height
                        StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: row.model.statusKind; text: row.model.statusLabel }
                    }
                }
            }
        }

        EmptyState {
            visible: Sites.count === 0
            anchors.centerIn: parent
            iconName: "map-pin"
            title: qsTr("No sites yet")
            message: qsTr("Add the stores, mine sites, workshops and offices where equipment and GCP banners are kept.")
            actionText: Sites.canManage ? qsTr("Add site") : ""
            onAction: siteSheet.openNew()
        }
    }

    SiteSheet { id: siteSheet }
}
