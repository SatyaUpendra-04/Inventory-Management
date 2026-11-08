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
    // Shown by Component.onCompleted, already maximised, so it never flashes small first.
    visible: false
    title: qsTr("Inventory Management")
    color: Theme.colors.window
    font.family: Theme.type.family
    font.pixelSize: Theme.type.body

    // Changes the theme with a cross-fade instead of an abrupt flash.
    function transitionTheme(change) {
        if (Theme.reducedMotion || !window.inApp) { change(); return }
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

    readonly property bool inApp: Session.stage === "app"
    readonly property var gatePages: ({
        setup: "pages/SetupPage.qml", signIn: "pages/LoginPage.qml",
        changePassword: "pages/ChangePasswordPage.qml", completeProfile: "pages/CompleteProfilePage.qml"
    })

    RowLayout {
        id: shellLayout
        anchors.fill: parent
        spacing: 0
        visible: window.inApp
        opacity: window.inApp ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.motion.page; easing.type: Easing.OutCubic } }

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

    Component.onCompleted: StartMaximized ? showMaximized() : show()

    Shortcut { sequence: "Ctrl+,"; onActivated: Shell.navigate("settings") }
    // F11: true full screen (no title bar or taskbar) and back to a maximised window.
    Shortcut {
        sequences: ["F11"]
        onActivated: window.visibility === Window.FullScreen ? window.showMaximized() : window.showFullScreen()
    }
    Shortcut { sequence: "Ctrl+Shift+L"; onActivated: window.transitionTheme(function () { Theme.setMode(Theme.dark ? "light" : "dark") }) }

    ToastHost {
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.bottomMargin: Theme.space.lg
        anchors.rightMargin: Theme.space.lg
        z: 900
    }

    // Setup, sign-in, password and profile screens shown before the app.
    Loader {
        id: gate
        objectName: "gate"
        anchors.fill: parent
        active: !window.inApp
        source: window.gatePages[Session.stage] || ""
        z: 800
        onLoaded: {
            item.opacity = 0
            gateFade.restart()
        }
        NumberAnimation { id: gateFade; target: gate.item; property: "opacity"; to: 1; duration: Theme.motion.page; easing.type: Easing.OutCubic }
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
