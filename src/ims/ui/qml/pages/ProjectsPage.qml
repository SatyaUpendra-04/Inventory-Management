import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Projects: survey jobs with their site, crew, flights and status.
Item {
    id: page

    property var section: ({})
    readonly property var columns: Projects.crewView ? [0.27, 0.18, 0.16, 0.13, 0.17, 0.09]
                                                     : [0.30, 0.20, 0.17, 0.14, 0.10, 0.09]

    Component.onCompleted: Projects.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm

        AppTextField {
            width: 260
            placeholder: qsTr("Search code, name, client or site")
            iconName: "search"
            onTextChanged: Projects.setSearch(text)
        }
        SegmentedControl {
            id: filter
            segmentWidth: 116
            value: Projects.filter
            options: Projects.filterOptions
            onActivated: function (v) { Projects.setFilter(v) }
        }
        Item { width: Math.max(0, toolbar.width - x - newButton.width - Theme.space.sm); height: 1 }
        AppButton {
            id: newButton
            visible: Projects.canManage
            variant: "primary"
            iconName: "plus"
            text: qsTr("New project")
            onClicked: formSheet.openNew()
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
                model: Projects.crewView
                       ? [qsTr("Project"), qsTr("Site"), qsTr("Dates"), qsTr("Your role"), qsTr("Your work"), qsTr("Status")]
                       : [qsTr("Project"), qsTr("Site"), qsTr("Dates"), qsTr("Chief pilot"), qsTr("Flights"), qsTr("Status")]
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
            model: Projects.model
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            delegate: AbstractButton {
                id: row
                required property var model
                width: list.width
                height: 54
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                leftPadding: Theme.space.md
                rightPadding: Theme.space.md
                Accessible.name: model.code + " " + model.name
                onClicked: projectSheet.show(model.projectId)

                background: Rectangle {
                    color: row.hovered ? Theme.colors.element : "transparent"
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                    FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                }
                contentItem: Row {
                    readonly property real w: row.availableWidth
                    Column {
                        width: parent.w * page.columns[0]
                        anchors.verticalCenter: parent.verticalCenter
                        Txt { width: parent.width - Theme.space.sm; text: row.model.code; variant: "bodyStrong"; elide: Text.ElideRight }
                        Txt { width: parent.width - Theme.space.sm; text: row.model.name; variant: "caption"; muted: true; elide: Text.ElideRight }
                    }
                    Txt { width: parent.w * page.columns[1]; height: row.height; text: row.model.site; elide: Text.ElideRight; rightPadding: Theme.space.sm }
                    Txt { width: parent.w * page.columns[2]; height: row.height; text: row.model.dates; variant: "caption" }
                    readonly property string col3: Projects.crewView ? row.model.myRole : row.model.chiefPilot
                    readonly property string col4: Projects.crewView ? row.model.myWork : row.model.flights
                    Txt { width: parent.w * page.columns[3]; height: row.height; text: parent.col3 || "—"; muted: !parent.col3; elide: Text.ElideRight; rightPadding: Theme.space.sm }
                    Txt { width: parent.w * page.columns[4]; height: row.height; text: parent.col4 || "—"; muted: !parent.col4; variant: "caption"; elide: Text.ElideRight; font.features: { "tnum": 1 } }
                    Item {
                        width: parent.w * page.columns[5]
                        height: row.height
                        StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: row.model.statusKind; text: row.model.statusLabel }
                    }
                }
            }
        }

        EmptyState {
            visible: Projects.count === 0
            anchors.centerIn: parent
            iconName: "briefcase"
            title: Projects.total === 0 ? qsTr("No projects yet")
                   : Projects.filter === "assigned" ? qsTr("Nothing assigned to you right now")
                   : Projects.filter === "completed" && Projects.crewView ? qsTr("No completed projects yet")
                   : qsTr("No projects match")
            message: Projects.total === 0
                     ? (Projects.canManage ? qsTr("Create a project for each survey job: the mine site, dates and crew. Equipment is then checked out to it.")
                                           : qsTr("Projects appear here when an administrator creates them."))
                     : Projects.filter === "assigned"
                       ? qsTr("Projects show here when you are named as chief pilot or lead surveyor, or are in the crew that takes equipment out.")
                       : Projects.filter === "completed" && Projects.crewView
                         ? qsTr("Projects you worked on move here when they are completed.")
                         : qsTr("Try another filter or search.")
            actionText: Projects.total === 0 && Projects.canManage ? qsTr("New project") : ""
            onAction: formSheet.openNew()
        }
    }

    ProjectFormSheet { id: formSheet }
    ProjectSheet {
        id: projectSheet
        onEditRequested: function (detail) { formSheet.openEdit(detail) }
    }
}
