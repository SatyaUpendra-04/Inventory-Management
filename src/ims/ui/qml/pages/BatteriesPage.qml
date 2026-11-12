import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Batteries: every pack's cycles against its limit, health, last check and what it needs.
Item {
    id: page

    property var section: ({})
    readonly property var columns: [0.17, 0.17, 0.22, 0.13, 0.13, 0.18]

    Component.onCompleted: Batteries.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm
        SegmentedControl {
            id: tabs
            segmentWidth: 120
            value: "batteries"
            options: Batteries.canManage ? [{ value: "batteries", label: qsTr("Batteries") }, { value: "limits", label: qsTr("Limits") }]
                                         : [{ value: "batteries", label: qsTr("Batteries") }]
            onActivated: function (v) { tabs.value = v }
        }
        AppTextField {
            visible: tabs.value === "batteries"
            width: 240
            placeholder: qsTr("Search tag or serial")
            iconName: "search"
            onTextChanged: Batteries.setSearch(text)
        }
        SegmentedControl {
            visible: tabs.value === "batteries"
            segmentWidth: 150
            value: Batteries.filter
            options: [{ value: "all", label: qsTr("All") },
                      { value: "attention", label: Batteries.attentionCount ? qsTr("Need attention %1").arg(Batteries.attentionCount) : qsTr("Need attention") }]
            onActivated: function (v) { Batteries.setFilter(v) }
        }
    }

    StackLayout {
        anchors.top: toolbar.bottom
        anchors.topMargin: Theme.space.md
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space.xl
        x: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        currentIndex: tabs.value === "batteries" ? 0 : 1

        Card {
            elevation: "low"
            radius: Theme.radius.md
            Row {
                id: headings
                x: Theme.space.md
                width: parent.width - Theme.space.md * 2
                height: 38
                Repeater {
                    model: [qsTr("Battery"), qsTr("Kind"), qsTr("Cycles"), qsTr("Health"), qsTr("Last check"), qsTr("Condition")]
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
                model: Batteries.model
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {}
                delegate: AbstractButton {
                    id: row
                    required property var model
                    width: list.width
                    height: 52
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    leftPadding: Theme.space.md
                    rightPadding: Theme.space.md
                    opacity: model.retired ? 0.55 : 1
                    Accessible.name: model.tag
                    onClicked: batterySheet.show(model.assetId)
                    background: Rectangle {
                        color: row.hovered ? Theme.colors.element : "transparent"
                        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                        FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                    }
                    contentItem: Row {
                        readonly property real w: row.availableWidth
                        Txt { width: parent.w * page.columns[0]; height: row.height; text: row.model.tag; variant: "bodyStrong" }
                        Txt { width: parent.w * page.columns[1]; height: row.height; text: row.model.family; muted: true }
                        Item {
                            width: parent.w * page.columns[2]
                            height: row.height
                            Column {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width - Theme.space.lg
                                spacing: 4
                                Txt { text: row.model.cyclesText; variant: "caption"; font.features: { "tnum": 1 } }
                                Rectangle {
                                    width: parent.width
                                    height: 6
                                    radius: 3
                                    color: Theme.colors.element
                                    Rectangle {
                                        width: parent.width * row.model.cycleShare
                                        height: parent.height
                                        radius: 3
                                        color: row.model.cycleShare >= 1 ? Theme.colors.dangerSolid
                                             : row.model.cycleShare >= 0.9 ? Theme.colors.warningSolid : Theme.colors.accent
                                    }
                                }
                            }
                        }
                        Txt { width: parent.w * page.columns[3]; height: row.height; text: row.model.health; font.features: { "tnum": 1 } }
                        Txt { width: parent.w * page.columns[4]; height: row.height; text: row.model.lastCheck || qsTr("Never"); muted: !row.model.lastCheck; variant: "caption" }
                        Item { width: parent.w * page.columns[5]; height: row.height
                               StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: row.model.conditionKind; text: row.model.conditionLabel } }
                    }
                }
            }
            EmptyState {
                visible: Batteries.count === 0
                anchors.centerIn: parent
                iconName: "battery"
                title: Batteries.filter === "attention" ? qsTr("Every battery is fine") : qsTr("No batteries registered")
                message: qsTr("Register drone, receiver and controller batteries on the Equipment page. Each keeps its own cycles and health wherever it is used.")
            }
        }

        // ------------------------------------------------------------ limits
        Card {
            elevation: "low"
            radius: Theme.radius.md
            Column {
                x: Theme.space.md
                y: Theme.space.md
                width: parent.width - Theme.space.md * 2
                spacing: Theme.space.sm
                Txt {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    muted: true
                    text: qsTr("Starting values: set them from each manufacturer's datasheet. A battery is grounded at its cycle limit or when a measured health falls below the limit; servicing never resets either.")
                }
                Repeater {
                    model: Batteries.policies
                    delegate: Rectangle {
                        id: policy
                        required property var modelData
                        width: parent.width
                        height: 64
                        radius: Theme.radius.sm
                        color: Theme.colors.element
                        Row {
                            x: Theme.space.md
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: Theme.space.md
                            Txt { width: 200; anchors.verticalCenter: parent.verticalCenter; text: policy.modelData.type; variant: "bodyStrong" }
                            AppTextField { id: limit; width: 130; label: qsTr("Cycle limit"); text: policy.modelData.cycleLimit }
                            AppTextField { id: floor; width: 130; label: qsTr("Health limit %"); text: policy.modelData.healthFloor }
                            AppTextField { id: idle; width: 170; label: qsTr("Storage reminder (days)"); text: policy.modelData.idleDays }
                            AppButton {
                                anchors.bottom: parent.bottom
                                text: qsTr("Save")
                                enabled: !Tasks.busy
                                onClicked: Batteries.updatePolicy(policy.modelData.policyId, policy.modelData.version,
                                                                  { cycleLimit: limit.text, healthFloor: floor.text, idleDays: idle.text,
                                                                    notes: policy.modelData.notes })
                            }
                        }
                    }
                }
                ErrorBanner { text: Batteries.error }
            }
        }
    }

    BatterySheet { id: batterySheet }
}
