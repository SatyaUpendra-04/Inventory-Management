import QtQuick
import QtQuick.Controls.Basic
import "../components"

// The alert centre: everything that needs attention, grouped, most urgent first.
Sheet {
    id: sheet

    width: Math.min(720, parent ? parent.width - 64 : 720)
    title: qsTr("Alerts")
    subtitle: Alerts.alerts.length === 0 ? qsTr("Nothing needs attention.")
              : Alerts.urgentCount ? qsTr("%n need(s) action now", "", Alerts.urgentCount)
                                   : qsTr("%n thing(s) to keep an eye on", "", Alerts.alerts.length)

    function show() {
        Alerts.refresh()
        open()
    }

    Column {
        width: parent.width
        spacing: Theme.space.md

        EmptyState {
            visible: Alerts.alerts.length === 0
            anchors.horizontalCenter: parent.horizontalCenter
            iconName: "circle-check"
            title: qsTr("All clear")
            message: qsTr("Maintenance, batteries, calibration, documents, certificates and stock are all in order.")
        }

        Repeater {
            model: Alerts.groups
            delegate: Column {
                id: group
                required property var modelData
                width: parent.width
                spacing: 4
                Row {
                    spacing: Theme.space.xs
                    Icon { anchors.verticalCenter: parent.verticalCenter; name: group.modelData.icon; size: 16; color: Theme.colors.textMuted }
                    Txt { text: group.modelData.label; variant: "headline" }
                    Badge { anchors.verticalCenter: parent.verticalCenter; count: group.modelData.alerts.length; kind: "accent" }
                }
                Repeater {
                    model: group.modelData.alerts
                    delegate: AbstractButton {
                        id: item
                        required property var modelData
                        width: group.width
                        height: Math.max(44, line.implicitHeight + Theme.space.sm * 2)
                        hoverEnabled: true
                        focusPolicy: Qt.StrongFocus
                        Accessible.name: modelData.title + ": " + modelData.message
                        onClicked: { Shell.navigate(modelData.section); sheet.close() }
                        background: Rectangle {
                            radius: Theme.radius.sm
                            color: item.hovered ? Theme.colors.elementHover : Theme.colors.element
                            Rectangle {
                                width: 3
                                height: parent.height - 12
                                anchors.verticalCenter: parent.verticalCenter
                                x: 4
                                radius: 1.5
                                color: item.modelData.severity === "danger" ? Theme.colors.dangerSolid
                                     : item.modelData.severity === "warning" ? Theme.colors.warningSolid : Theme.colors.infoSolid
                            }
                            FocusRing { show: item.visualFocus }
                        }
                        contentItem: Column {
                            id: line
                            leftPadding: Theme.space.md
                            topPadding: Theme.space.sm
                            spacing: 2
                            Txt { width: item.width - Theme.space.xl * 2; text: item.modelData.title; variant: "bodyStrong"; elide: Text.ElideRight }
                            Txt { width: item.width - Theme.space.xl * 2; text: item.modelData.message; wrapMode: Text.WordWrap
                                  color: item.modelData.severity === "danger" ? Theme.colors.dangerText : Theme.colors.text }
                        }
                    }
                }
            }
        }
        ErrorBanner { text: Alerts.error }
    }

    actions: [ AppButton { text: qsTr("Close"); onClicked: sheet.close() } ]
}
