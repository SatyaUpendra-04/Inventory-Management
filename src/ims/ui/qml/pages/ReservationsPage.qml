import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Reservations: requests waiting for approval, what is booked, and a four-week calendar.
Item {
    id: page

    property var section: ({})
    readonly property var columns: [0.27, 0.13, 0.30, 0.13, 0.17]

    Component.onCompleted: Reservations.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm

        SegmentedControl {
            id: view
            segmentWidth: 110
            value: "list"
            options: [{ value: "list", label: qsTr("List"), icon: "layers" },
                      { value: "calendar", label: qsTr("Calendar"), icon: "calendar" }]
            onActivated: function (v) { view.value = v }
        }
        SegmentedControl {
            visible: view.value === "list"
            segmentWidth: 104
            value: Reservations.filter
            options: Reservations.filterOptions
            onActivated: function (v) { Reservations.setFilter(v) }
        }
        SegmentedControl {
            id: calendarMode
            visible: view.value === "calendar"
            segmentWidth: 130
            value: "equipment"
            options: [{ value: "equipment", label: qsTr("By equipment") },
                      { value: "project", label: qsTr("By project") }]
            onActivated: function (v) { calendarMode.value = v }
        }
        Item { width: Math.max(0, toolbar.width - x - newButton.width - Theme.space.sm); height: 1 }
        AppButton {
            id: newButton
            visible: Reservations.canRequest
            variant: "primary"
            iconName: "calendar"
            text: qsTr("Reserve equipment")
            onClicked: reservationSheet.openNew("")
        }
    }

    StackLayout {
        anchors.top: toolbar.bottom
        anchors.topMargin: Theme.space.md
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space.xl
        x: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        currentIndex: view.value === "list" ? 0 : 1

        // ------------------------------------------------------------ list
        Card {
            elevation: "low"
            radius: Theme.radius.md

            Row {
                id: headings
                x: Theme.space.md
                width: parent.width - Theme.space.md * 2
                height: 38
                Repeater {
                    model: [qsTr("Project"), qsTr("Dates"), qsTr("Equipment"), qsTr("Asked by"), qsTr("Status")]
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
                model: Reservations.model
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
                    Accessible.name: model.project + " " + model.dates
                    onClicked: reservationSheet.show(model.reservationId)

                    background: Rectangle {
                        color: row.hovered ? Theme.colors.element : "transparent"
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                        FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                    }
                    contentItem: Row {
                        readonly property real w: row.availableWidth
                        Txt { width: parent.w * page.columns[0]; height: row.height; text: row.model.project; variant: "bodyStrong"; elide: Text.ElideRight; rightPadding: Theme.space.sm }
                        Txt { width: parent.w * page.columns[1]; height: row.height; text: row.model.dates; font.features: { "tnum": 1 } }
                        Txt { width: parent.w * page.columns[2]; height: row.height
                              text: row.model.items + (row.model.gcp ? qsTr("  ·  %1 GCP").arg(row.model.gcp) : "")
                              elide: Text.ElideRight; rightPadding: Theme.space.sm }
                        Txt { width: parent.w * page.columns[3]; height: row.height; text: row.model.mine ? qsTr("You") : row.model.requestedBy; muted: true; elide: Text.ElideRight }
                        Item {
                            width: parent.w * page.columns[4]
                            height: row.height
                            StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: row.model.statusKind; text: row.model.statusLabel }
                        }
                    }
                }
            }

            EmptyState {
                visible: Reservations.count === 0
                anchors.centerIn: parent
                iconName: "calendar"
                title: Reservations.filter === "pending" ? qsTr("No requests waiting")
                       : Reservations.filter === "upcoming" ? qsTr("Nothing booked yet") : qsTr("No reservations yet")
                message: qsTr("Book equipment, kits and GCP banners for a project's dates. Approved bookings cannot be double-booked, and turn into a check-out when the crew leaves.")
                actionText: Reservations.canRequest ? qsTr("Reserve equipment") : ""
                onAction: reservationSheet.openNew("")
            }
        }

        // ------------------------------------------------------------ calendar
        Card {
            elevation: "low"
            radius: Theme.radius.md

            Item {
                id: calendarBar
                x: Theme.space.md
                y: Theme.space.sm
                width: parent.width - Theme.space.md * 2
                height: 36
                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.space.xs
                    IconButton { iconName: "chevron-left"; tip: qsTr("Previous week"); onClicked: Reservations.shiftCalendar(-1) }
                    IconButton { iconName: "chevron-right"; tip: qsTr("Next week"); onClicked: Reservations.shiftCalendar(1) }
                    AppButton { compact: true; variant: "ghost"; text: qsTr("This week"); onClicked: Reservations.calendarToday() }
                    Txt { anchors.verticalCenter: parent.verticalCenter; leftPadding: Theme.space.sm
                          text: Reservations.calendar.title || ""; variant: "headline" }
                }
                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.space.md
                    Repeater {
                        model: [{ kind: "approved", label: qsTr("Booked") }, { kind: "requested", label: qsTr("Requested") },
                                { kind: "out", label: qsTr("Out on a project") }]
                        delegate: Row {
                            required property var modelData
                            spacing: 6
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 22; height: 12; radius: 6
                                color: timeline.fill(modelData.kind)
                                border.width: modelData.kind === "requested" ? 1 : 0
                                border.color: Theme.colors.warningBorder
                            }
                            Txt { text: modelData.label; variant: "caption"; muted: true }
                        }
                    }
                }
            }
            Timeline {
                id: timeline
                anchors.fill: parent
                anchors.topMargin: calendarBar.height + Theme.space.sm * 2
                anchors.leftMargin: Theme.space.xs
                anchors.rightMargin: Theme.space.xs
                days: Reservations.calendar.days || []
                rows: calendarMode.value === "equipment" ? (Reservations.calendar.assets || [])
                                                         : (Reservations.calendar.projects || [])
                onBarClicked: function (reservationId, deploymentId) {
                    if (reservationId) reservationSheet.show(reservationId)
                    else if (deploymentId) returnSheet.show(deploymentId)
                }
            }
        }
    }

    ReservationSheet { id: reservationSheet }
    ReturnSheet { id: returnSheet }
}
