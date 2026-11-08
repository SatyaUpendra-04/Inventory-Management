import QtQuick
import "../components"

// Stand-in for sections delivered in later sprints.
Item {
    id: page

    property var section: ({})

    EmptyState {
        anchors.centerIn: parent
        iconName: page.section.icon || "sparkles"
        title: qsTr("%1 arrives in Sprint %2").arg(page.section.title || "").arg(page.section.sprint || "")
        message: page.section.summary || ""
        actionText: qsTr("Open design gallery")
        onAction: Shell.navigate("gallery")
    }
}
