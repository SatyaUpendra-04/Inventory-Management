import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Grouped navigation. The selection highlight glides to the chosen item.
Rectangle {
    id: sidebar

    implicitWidth: 248
    color: Theme.colors.sidebar

    function indexOfKey(key) {
        for (var i = 0; i < Shell.sections.length; ++i)
            if (Shell.sections[i].key === key) return i
        return 0
    }

    // Subtle vertical sheen, standing in for macOS vibrancy.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.alpha(Theme.colors.accent, Theme.dark ? 0.05 : 0.035) }
            GradientStop { position: 0.45; color: "transparent" }
        }
    }

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.colors.divider
    }

    Row {
        id: brand
        x: Theme.space.md
        y: Theme.space.md
        spacing: Theme.space.sm
        Rectangle {
            width: 34
            height: 34
            radius: 9
            color: Theme.colors.accent
            Icon { anchors.centerIn: parent; name: "drone"; size: 20; color: Theme.colors.onAccent }
        }
        Column {
            anchors.verticalCenter: parent.verticalCenter
            Txt { text: qsTr("Inventory"); variant: "bodyStrong" }
            Txt { text: qsTr("Drone & survey fleet"); variant: "caption"; muted: true }
        }
    }

    ListView {
        id: nav
        objectName: "sidebarNav"

        anchors.top: brand.bottom
        anchors.topMargin: Theme.space.md
        anchors.bottom: profile.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: Theme.space.xs
        anchors.rightMargin: Theme.space.xs + 1
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: Shell.sections
        currentIndex: sidebar.indexOfKey(Shell.current)
        activeFocusOnTab: true
        keyNavigationEnabled: false
        highlightFollowsCurrentItem: false
        Accessible.role: Accessible.List
        Accessible.name: qsTr("Sections")

        Keys.onUpPressed: Shell.step(-1)
        Keys.onDownPressed: Shell.step(1)

        section.property: "group"
        section.delegate: Txt {
            required property string section
            width: ListView.view.width
            height: 30
            leftPadding: Theme.space.sm
            topPadding: 8
            text: section
            variant: "caption"
            font.weight: Theme.type.semibold
            muted: true
        }

        highlight: Rectangle {
            width: nav.width
            height: nav.currentItem ? nav.currentItem.height : 0
            y: nav.currentItem ? nav.currentItem.y : 0
            radius: Theme.radius.sm
            color: Theme.colors.accentSubtle
            Behavior on y {
                enabled: !Theme.reducedMotion
                SpringAnimation { spring: Theme.motion.springStiffness; damping: Theme.motion.springDamping; epsilon: 0.25 }
            }
            FocusRing { show: nav.activeFocus }
        }

        delegate: AbstractButton {
            id: item
            required property var modelData
            required property int index
            readonly property bool current: Shell.current === modelData.key

            width: nav.width
            height: 34
            hoverEnabled: true
            focusPolicy: Qt.NoFocus
            Accessible.name: modelData.title
            Accessible.role: Accessible.ListItem
            onClicked: { Shell.navigate(modelData.key); nav.forceActiveFocus(Qt.MouseFocusReason) }

            background: Rectangle {
                radius: Theme.radius.sm
                color: item.hovered && !item.current ? Theme.colors.element : "transparent"
                Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
            }
            contentItem: Row {
                leftPadding: Theme.space.sm
                spacing: Theme.space.sm
                Icon {
                    name: item.modelData.icon
                    size: 18
                    color: item.current ? Theme.colors.accentText : Theme.colors.textMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
                Txt {
                    text: item.modelData.title
                    font.weight: item.current ? Theme.type.semibold : Theme.type.regular
                    color: item.current ? Theme.colors.accentText : Theme.colors.text
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }

    Rectangle {
        id: profile
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.space.xs
        anchors.rightMargin: Theme.space.xs + 1
        height: 52
        radius: Theme.radius.md
        color: "transparent"

        Row {
            anchors.verticalCenter: parent.verticalCenter
            x: Theme.space.sm
            spacing: Theme.space.sm
            Rectangle {
                width: 32
                height: 32
                radius: 16
                color: Theme.colors.accentSubtleHover
                Txt {
                    anchors.centerIn: parent
                    text: "DP"
                    variant: "caption"
                    font.weight: Theme.type.semibold
                    color: Theme.colors.accentText
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                Txt { text: qsTr("Design preview"); variant: "bodyStrong" }
                Txt { text: qsTr("Sign-in arrives in Sprint 3"); variant: "caption"; muted: true }
            }
        }
    }
}
