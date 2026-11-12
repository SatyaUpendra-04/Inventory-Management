import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Page title, search and quick actions.
Rectangle {
    id: toolbar

    signal toggleTheme()

    implicitHeight: 60
    color: Theme.colors.window

    Rectangle {
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.colors.divider
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: Theme.space.lg
        anchors.verticalCenter: parent.verticalCenter
        anchors.right: actions.left
        anchors.rightMargin: Theme.space.md
        spacing: 1
        Txt {
            text: Shell.currentSection.title
            variant: "title3"
            elide: Text.ElideRight
            width: parent.width
        }
        Txt {
            text: Shell.currentSection.summary
            variant: "caption"
            muted: true
            elide: Text.ElideRight
            width: parent.width
        }
    }

    Row {
        id: actions
        anchors.right: parent.right
        anchors.rightMargin: Theme.space.lg
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.space.xs

        AppTextField {
            width: 240
            placeholder: qsTr("Search equipment, projects, people")
            iconName: "search"
            anchors.verticalCenter: parent.verticalCenter
        }
        IconButton {
            iconName: "bell"
            tip: qsTr("Alerts")
            anchors.verticalCenter: parent.verticalCenter
            Accessible.name: Alerts.count ? qsTr("Alerts, %n need attention", "", Alerts.count) : qsTr("Alerts")
            onClicked: alertsSheet.show()
            Badge { count: Alerts.count; kind: Alerts.urgentCount ? "danger" : "accent"
                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: -2 }
        }
        IconButton {
            iconName: Theme.dark ? "sun" : "moon"
            tip: Theme.dark ? qsTr("Switch to light") : qsTr("Switch to dark")
            anchors.verticalCenter: parent.verticalCenter
            onClicked: toolbar.toggleTheme()
        }
    }

    AlertsSheet { id: alertsSheet }
}
