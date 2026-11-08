import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Deployments: what is out with crews right now, and the history of check-outs.
Item {
    id: page

    property var section: ({})
    readonly property var columns: [0.27, 0.12, 0.33, 0.16, 0.12]

    Component.onCompleted: Deployments.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm

        SegmentedControl {
            segmentWidth: 120
            value: Deployments.filter
            options: [{ value: "out", label: qsTr("Out now") }, { value: "all", label: qsTr("All") }]
            onActivated: function (v) { Deployments.setFilter(v) }
        }
        Txt {
            anchors.verticalCenter: parent.verticalCenter
            text: qsTr("%n deployment(s) out", "", Deployments.outCount)
            muted: true
        }
        Item { width: Math.max(0, toolbar.width - x - newButton.width - Theme.space.sm); height: 1 }
        AppButton {
            id: newButton
            visible: Deployments.canDeploy
            variant: "primary"
            iconName: "send"
            text: qsTr("Check out equipment")
            onClicked: checkout.openFor("")
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
                model: [qsTr("Project"), qsTr("Out on"), qsTr("Equipment"), qsTr("Crew"), qsTr("State")]
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
            model: Deployments.model
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
                Accessible.name: model.project
                onClicked: returnSheet.show(model.deploymentId)

                background: Rectangle {
                    color: row.hovered ? Theme.colors.element : "transparent"
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                    FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                }
                contentItem: Row {
                    readonly property real w: row.availableWidth
                    Txt { width: parent.w * page.columns[0]; height: row.height; text: row.model.project; variant: "bodyStrong"; elide: Text.ElideRight; rightPadding: Theme.space.sm }
                    Txt { width: parent.w * page.columns[1]; height: row.height; text: row.model.deployedOn; variant: "caption" }
                    Txt { width: parent.w * page.columns[2]; height: row.height; text: row.model.items + (row.model.gcp ? qsTr(" · %1 GCP").arg(row.model.gcp) : ""); elide: Text.ElideRight; rightPadding: Theme.space.sm }
                    Txt { width: parent.w * page.columns[3]; height: row.height; text: row.model.crew; muted: true; elide: Text.ElideRight; rightPadding: Theme.space.sm }
                    Item {
                        width: parent.w * page.columns[4]
                        height: row.height
                        StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: row.model.stateKind; text: row.model.stateLabel }
                    }
                }
            }
        }

        EmptyState {
            visible: Deployments.count === 0
            anchors.centerIn: parent
            iconName: "send"
            title: Deployments.filter === "out" ? qsTr("Nothing is out right now") : qsTr("No deployments yet")
            message: qsTr("Check equipment out to a project before the crew leaves; return it when they are back.")
            actionText: Deployments.canDeploy ? qsTr("Check out equipment") : ""
            onAction: checkout.openFor("")
        }
    }

    CheckoutSheet { id: checkout }
    ReturnSheet { id: returnSheet }
}
