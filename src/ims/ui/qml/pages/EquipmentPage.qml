import QtQuick
import QtQuick.Layouts
import "../components"

// Equipment: every registered asset, and the kits they are grouped into.
Item {
    id: page

    property var section: ({})

    SegmentedControl {
        id: tabs
        x: Theme.space.xl
        y: Theme.space.lg
        segmentWidth: 110
        value: "assets"
        options: [{ value: "assets", label: qsTr("Assets"), icon: "drone" },
                  { value: "kits", label: qsTr("Kits"), icon: "box" }]
        onActivated: function (v) { tabs.value = v }
    }

    StackLayout {
        anchors.top: tabs.bottom
        anchors.topMargin: Theme.space.md
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        currentIndex: tabs.value === "assets" ? 0 : 1

        AssetsView {}
        KitsView {}
    }
}
