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
        return -1  // a page outside the sidebar (e.g. My profile): highlight nothing
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

        // The focus ring is for keyboard users only, as on macOS: Tab or arrow keys
        // show it; a mouse click does not.
        property bool focusFromClick: false
        readonly property bool keyboardFocus: activeFocus && !focusFromClick
        onActiveFocusChanged: if (!activeFocus) focusFromClick = false
        Keys.onUpPressed: { focusFromClick = false; Shell.step(-1) }
        Keys.onDownPressed: { focusFromClick = false; Shell.step(1) }

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
            visible: nav.currentIndex >= 0
            width: nav.width
            height: nav.currentItem ? nav.currentItem.height : 0
            y: nav.currentItem ? nav.currentItem.y : 0
            radius: Theme.radius.sm
            color: Theme.colors.accentSubtle
            Behavior on y {
                enabled: !Theme.reducedMotion
                SpringAnimation { spring: Theme.motion.springStiffness; damping: Theme.motion.springDamping; epsilon: 0.25 }
            }
            FocusRing { inset: true; show: nav.activeFocus && nav.keyboardFocus }
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
            onClicked: {
                nav.focusFromClick = true
                nav.forceActiveFocus(Qt.MouseFocusReason)
                Shell.navigate(modelData.key)
            }

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

    AbstractButton {
        id: profile
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: Theme.space.xs
        anchors.rightMargin: Theme.space.xs + 1
        height: 52
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.name: qsTr("Account menu for %1").arg(Session.displayName)
        onClicked: menu.open()

        background: Rectangle {
            radius: Theme.radius.md
            color: profile.hovered || menu.visible ? Theme.colors.element : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
            FocusRing { show: profile.visualFocus; baseRadius: Theme.radius.md }
        }
        contentItem: Row {
            leftPadding: Theme.space.xs
            spacing: Theme.space.sm
            Avatar {
                size: 32
                source: Session.picture
                initials: Session.initials
                anchors.verticalCenter: parent.verticalCenter
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                width: profile.width - 80
                Txt { width: parent.width; text: Session.displayName; variant: "bodyStrong"; elide: Text.ElideRight }
                Txt { width: parent.width; text: Session.roleLabel; variant: "caption"; muted: true }
            }
            Icon { name: "chevron-up"; size: 16; color: Theme.colors.textMuted; anchors.verticalCenter: parent.verticalCenter }
        }

        AppPopover {
            id: menu
            y: -height - 6
            width: profile.width
            padding: Theme.space.xs
            Column {
                width: profile.width - Theme.space.xs * 2
                AppButton {
                    width: parent.width
                    variant: "ghost"
                    iconName: "user"
                    text: qsTr("My profile")
                    onClicked: { menu.close(); Shell.navigate("profile") }
                }
                AppButton {
                    width: parent.width
                    variant: "ghost"
                    iconName: "log-out"
                    text: qsTr("Sign out")
                    onClicked: { menu.close(); Session.signOut() }
                }
            }
        }
    }
}
