import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Maintenance: what is due across the fleet, defects, work orders and the programme.
Item {
    id: page

    property var section: ({})

    Component.onCompleted: Maintenance.checkOverdue()

    component ListCard: Card { elevation: "low"; radius: Theme.radius.md }

    Row {
        id: toolbar
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm
        SegmentedControl {
            id: tabs
            segmentWidth: 128
            value: "due"
            options: [
                { value: "due", label: Maintenance.overdueCount ? qsTr("Due · %1 overdue").arg(Maintenance.overdueCount) : qsTr("Due") },
                { value: "defects", label: Maintenance.openDefects ? qsTr("Defects %1").arg(Maintenance.openDefects) : qsTr("Defects") },
                { value: "orders", label: Maintenance.openOrders ? qsTr("Work orders %1").arg(Maintenance.openOrders) : qsTr("Work orders") },
                { value: "programme", label: qsTr("Programme") }
            ]
            onActivated: function (v) { tabs.value = v }
        }
        Item { width: Math.max(0, toolbar.width - x - addTask.width - Theme.space.sm); height: 1 }
        AppButton {
            id: addTask
            visible: Maintenance.canManage && tabs.value === "programme"
            variant: "primary"
            iconName: "plus"
            text: qsTr("Add task")
            onClicked: taskSheet.openNew()
        }
    }

    StackLayout {
        anchors.top: toolbar.bottom
        anchors.topMargin: Theme.space.md
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space.xl
        x: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        currentIndex: ["due", "defects", "orders", "programme"].indexOf(tabs.value)

        // ============================================================ due
        ListCard {
            ListView {
                id: dueList
                anchors.fill: parent
                anchors.margins: Theme.space.xs
                clip: true
                model: Maintenance.due
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                delegate: Item {
                    id: dueRow
                    required property var modelData
                    width: dueList.width
                    height: 56
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                    Row {
                        x: Theme.space.sm
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Column {
                            width: 190
                            anchors.verticalCenter: parent.verticalCenter
                            Txt { text: dueRow.modelData.tag; variant: "bodyStrong" }
                            Txt { text: dueRow.modelData.type; variant: "caption"; muted: true }
                        }
                        Column {
                            width: 280
                            anchors.verticalCenter: parent.verticalCenter
                            Txt { width: parent.width; text: dueRow.modelData.task; elide: Text.ElideRight }
                            Txt { width: parent.width; text: dueRow.modelData.intervals; variant: "caption"; muted: true }
                        }
                        Item { width: 130; height: 56
                               StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: dueRow.modelData.stateKind; text: dueRow.modelData.stateLabel } }
                        Txt { width: 200; height: 56; text: dueRow.modelData.summary; font.features: { "tnum": 1 }
                              color: dueRow.modelData.state === "overdue" ? Theme.colors.dangerText : Theme.colors.text }
                        Txt { width: 150; height: 56; text: dueRow.modelData.lastDone ? qsTr("Last %1").arg(dueRow.modelData.lastDone) : qsTr("Never recorded")
                              variant: "caption"; muted: true }
                    }
                    AppButton {
                        visible: Maintenance.canManage && !dueRow.modelData.lifeLimit
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.space.sm
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        text: qsTr("Work order…")
                        onClicked: orderSheet.openNew(dueRow.modelData.assetId, dueRow.modelData.tag,
                                                      dueRow.modelData.task, [dueRow.modelData.taskId], [])
                    }
                    Txt {
                        visible: dueRow.modelData.lifeLimit
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.space.sm
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Replace the part")
                        variant: "caption"
                        color: Theme.colors.dangerText
                    }
                }
            }
            EmptyState {
                visible: Maintenance.due.length === 0
                anchors.centerIn: parent
                iconName: "wrench"
                title: qsTr("Nothing due")
                message: qsTr("Tasks appear here as they come due by hours, cycles, landings or days. Overdue tasks ground the item automatically.")
            }
        }

        // ============================================================ defects
        ListCard {
            ListView {
                id: defectList
                anchors.fill: parent
                anchors.margins: Theme.space.xs
                clip: true
                model: Maintenance.defects
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                delegate: AbstractButton {
                    id: defectRow
                    required property var modelData
                    width: defectList.width
                    height: 58
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    opacity: modelData.open ? 1 : 0.6
                    Accessible.name: modelData.number
                    onClicked: defectSheet.show(modelData)
                    background: Rectangle {
                        color: defectRow.hovered ? Theme.colors.element : "transparent"
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                        FocusRing { show: defectRow.visualFocus; anchors.margins: 2; baseRadius: 4 }
                    }
                    contentItem: Row {
                        leftPadding: Theme.space.sm
                        spacing: Theme.space.md
                        Txt { width: 84; height: 58; text: defectRow.modelData.number; variant: "bodyStrong" }
                        Column {
                            width: 170
                            anchors.verticalCenter: parent.verticalCenter
                            Txt { text: defectRow.modelData.tag; variant: "bodyStrong" }
                            Txt { width: parent.width; text: defectRow.modelData.type; variant: "caption"; muted: true; elide: Text.ElideRight }
                        }
                        Column {
                            width: Math.max(200, defectList.width - 84 - 170 - 160 - 200 - Theme.space.md * 5)
                            anchors.verticalCenter: parent.verticalCenter
                            Txt { width: parent.width; text: defectRow.modelData.description; elide: Text.ElideRight }
                            Txt { width: parent.width; variant: "caption"; muted: true; elide: Text.ElideRight
                                  text: defectRow.modelData.limitation ? qsTr("Limitation: %1 until %2").arg(defectRow.modelData.limitation).arg(defectRow.modelData.deferredUntil)
                                                                         : defectRow.modelData.reported }
                        }
                        Item { width: 160; height: 58
                               StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: defectRow.modelData.stateKind; text: defectRow.modelData.stateLabel } }
                    }
                }
            }
            EmptyState {
                visible: Maintenance.defects.length === 0
                anchors.centerIn: parent
                iconName: "alert"
                title: qsTr("No defects reported")
                message: qsTr("Report a defect from an item's sheet, or when returning equipment from a project.")
            }
        }

        // ============================================================ work orders
        ListCard {
            ListView {
                id: orderList
                anchors.fill: parent
                anchors.margins: Theme.space.xs
                clip: true
                model: Maintenance.orders
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                delegate: AbstractButton {
                    id: orderRow
                    required property var modelData
                    width: orderList.width
                    height: 52
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    opacity: modelData.open ? 1 : 0.6
                    Accessible.name: modelData.number
                    onClicked: orderSheet.show(modelData.workOrderId)
                    background: Rectangle {
                        color: orderRow.hovered ? Theme.colors.element : "transparent"
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                        FocusRing { show: orderRow.visualFocus; anchors.margins: 2; baseRadius: 4 }
                    }
                    contentItem: Row {
                        leftPadding: Theme.space.sm
                        spacing: Theme.space.md
                        Txt { width: 84; height: 52; text: orderRow.modelData.number; variant: "bodyStrong" }
                        Txt { width: 110; height: 52; text: orderRow.modelData.tag; variant: "bodyStrong" }
                        Txt { width: Math.max(200, orderList.width - 84 - 110 - 170 - 190 - Theme.space.md * 5); height: 52
                              text: orderRow.modelData.title; elide: Text.ElideRight }
                        Txt { width: 170; height: 52; text: orderRow.modelData.opened; variant: "caption"; muted: true }
                        Item { width: 190; height: 52
                               StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: orderRow.modelData.stateKind; text: orderRow.modelData.stateLabel } }
                    }
                }
            }
            EmptyState {
                visible: Maintenance.orders.length === 0
                anchors.centerIn: parent
                iconName: "wrench"
                title: qsTr("No work orders yet")
                message: qsTr("Open one from a due task or a defect. Opening it takes the item into maintenance; an administrator signs it off to return it to service.")
            }
        }

        // ============================================================ programme
        ListCard {
            Flickable {
                anchors.fill: parent
                anchors.margins: Theme.space.md
                clip: true
                contentHeight: programmeColumn.height
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                Column {
                    id: programmeColumn
                    width: parent.width
                    spacing: Theme.space.md
                    Txt {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        muted: true
                        text: qsTr("Starting values: adjust them to each manufacturer's maintenance manual. Changes apply to every item of that kind.")
                    }
                    Repeater {
                        model: Maintenance.programme
                        delegate: Column {
                            id: group
                            required property var modelData
                            width: programmeColumn.width
                            spacing: 4
                            Txt { text: group.modelData.itemType; variant: "headline" }
                            Repeater {
                                model: group.modelData.tasks
                                delegate: AbstractButton {
                                    id: taskRow
                                    required property var modelData
                                    width: group.width
                                    height: 44
                                    hoverEnabled: true
                                    enabled: Maintenance.canManage
                                    opacity: modelData.active ? 1 : 0.55
                                    onClicked: taskSheet.openEdit(modelData)
                                    background: Rectangle { radius: Theme.radius.sm; color: taskRow.hovered ? Theme.colors.elementHover : Theme.colors.element }
                                    contentItem: Row {
                                        leftPadding: Theme.space.sm
                                        spacing: Theme.space.md
                                        Txt { width: 260; height: 44; text: taskRow.modelData.name; variant: "bodyStrong"; elide: Text.ElideRight }
                                        Txt { width: 260; height: 44; text: taskRow.modelData.intervals }
                                        Txt { width: 200; height: 44; text: taskRow.modelData.tolerance ? qsTr("Tolerance %1").arg(taskRow.modelData.tolerance) : ""; muted: true; variant: "caption" }
                                        Item { width: 120; height: 44
                                               StatusPill { visible: taskRow.modelData.lifeLimit || !taskRow.modelData.active; anchors.verticalCenter: parent.verticalCenter
                                                            kind: taskRow.modelData.lifeLimit ? "warning" : "neutral"
                                                            text: taskRow.modelData.lifeLimit ? qsTr("Life limit") : qsTr("Inactive") } }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    WorkOrderSheet { id: orderSheet }
    DefectSheet { id: defectSheet; onWorkOrderRequested: function (d) { orderSheet.openNew(d.assetId, d.tag, d.description, [], [d.defectId]) } }
    TaskSheet { id: taskSheet }
}
