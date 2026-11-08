import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "components"
import "shell"

ApplicationWindow {
    id: window

    width: 1360
    height: 860
    minimumWidth: 1024
    minimumHeight: 640
    visible: true
    title: qsTr("Inventory Management")
    color: Theme.colors.window
    font.family: Theme.type.family
    font.pixelSize: Theme.type.body

    // Changes the theme with a cross-fade instead of an abrupt flash.
    function transitionTheme(change) {
        if (Theme.reducedMotion || !shellLayout.visible) { change(); return }
        shellLayout.grabToImage(function (result) {
            fade.source = result.url
            fade.opacity = 1
            fade.visible = true
            change()
            fadeOut.restart()
        })
    }

    function showPage(section) {
        stack.replace(Qt.resolvedUrl("pages/" + section.page + ".qml"), { section: section })
    }

    function openSignInPreview() { signIn.active = true }
    function closeSignInPreview() { signIn.item.leave() }

    RowLayout {
        id: shellLayout
        anchors.fill: parent
        spacing: 0

        Sidebar { Layout.fillHeight: true }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Toolbar {
                Layout.fillWidth: true
                onToggleTheme: window.transitionTheme(function () { Theme.setMode(Theme.dark ? "light" : "dark") })
            }

            StackView {
                id: stack
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                Component.onCompleted: stack.push(Qt.resolvedUrl("pages/" + Shell.currentSection.page + ".qml"),
                                                  { section: Shell.currentSection }, StackView.Immediate)

                replaceEnter: Transition {
                    NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.page
                                      easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.motion.easing }
                    NumberAnimation { property: "y"; from: Theme.reducedMotion ? 0 : 14; to: 0; duration: Theme.motion.page
                                      easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.motion.easing }
                }
                replaceExit: Transition {
                    NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motion.micro }
                }
            }
        }
    }

    Connections {
        target: Shell
        function onCurrentChanged() { window.showPage(Shell.currentSection) }
    }

    Shortcut { sequence: "Ctrl+,"; onActivated: Shell.navigate("settings") }
    Shortcut { sequence: "Ctrl+Shift+L"; onActivated: window.transitionTheme(function () { Theme.setMode(Theme.dark ? "light" : "dark") }) }

    ToastHost {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 72
        anchors.rightMargin: Theme.space.lg
        z: 900
    }

    Loader {
        id: signIn
        anchors.fill: parent
        active: false
        z: 800
        source: "pages/LoginPage.qml"
        onLoaded: item.closed.connect(function () { signIn.active = false })
    }

    // Snapshot of the previous theme, faded out after a theme change.
    Image {
        id: fade
        anchors.fill: parent
        visible: false
        z: 1000
        NumberAnimation on opacity {
            id: fadeOut
            running: false
            to: 0
            duration: Theme.motion.standard + 60
            easing.type: Easing.InOutQuad
            onFinished: { fade.visible = false; fade.source = "" }
        }
    }
}
