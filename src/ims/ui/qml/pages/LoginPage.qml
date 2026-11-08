import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import "../components"

// Sign-in screen (design preview; real sign-in arrives in Sprint 3).
Rectangle {
    id: page

    signal closed()

    function leave() { outro.start() }

    color: Theme.colors.window
    opacity: 0
    Component.onCompleted: intro.start()

    NumberAnimation { id: intro; target: page; property: "opacity"; to: 1; duration: Theme.motion.page; easing.type: Easing.OutCubic }
    NumberAnimation { id: outro; target: page; property: "opacity"; to: 0; duration: Theme.motion.standard; onFinished: page.closed() }

    // Soft accent glow behind the card.
    Rectangle {
        width: 760
        height: 760
        radius: 380
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -80
        color: Theme.colors.accent
        opacity: Theme.dark ? 0.16 : 0.10
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
    }

    MouseArea { anchors.fill: parent }  // block clicks to the shell behind

    AppButton {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: Theme.space.lg
        variant: "ghost"
        iconName: "x"
        text: qsTr("Close preview")
        onClicked: page.leave()
    }

    Card {
        id: card
        width: 400
        height: form.implicitHeight + Theme.space.xl * 2
        anchors.centerIn: parent
        elevation: "high"
        radius: Theme.radius.lg + 4
        fill: Theme.colors.surfaceRaised
        padding: Theme.space.xl
        scale: page.opacity < 1 && !Theme.reducedMotion ? 0.97 + page.opacity * 0.03 : 1

        Column {
            id: form
            width: parent.width
            spacing: Theme.space.md

            Rectangle {
                width: 52
                height: 52
                radius: 14
                color: Theme.colors.accent
                anchors.horizontalCenter: parent.horizontalCenter
                Icon { anchors.centerIn: parent; name: "drone"; size: 28; color: Theme.colors.onAccent }
            }
            Column {
                width: parent.width
                spacing: 2
                Txt {
                    width: parent.width
                    text: qsTr("Sign in")
                    variant: "title2"
                    horizontalAlignment: Text.AlignHCenter
                }
                Txt {
                    width: parent.width
                    text: qsTr("Inventory Management")
                    muted: true
                    horizontalAlignment: Text.AlignHCenter
                }
            }

            Item { width: 1; height: 2 }

            AppTextField {
                id: username
                width: parent.width
                label: qsTr("Username")
                placeholder: qsTr("e.g. skumar")
                iconName: "user"
                field.focus: true
                onTextChanged: error = ""
                onAccepted: password.field.forceActiveFocus()
            }
            AppTextField {
                id: password
                width: parent.width
                label: qsTr("Password")
                placeholder: qsTr("Your password")
                iconName: "lock"
                password: true
                onTextChanged: error = ""
                onAccepted: signInButton.clicked()
            }

            AppButton {
                id: signInButton
                width: parent.width
                variant: "primary"
                text: qsTr("Sign in")
                onClicked: {
                    username.error = username.text.trim() === "" ? qsTr("Enter your username.") : ""
                    password.error = password.text === "" ? qsTr("Enter your password.") : ""
                    if (!username.error && !password.error)
                        Toasts.show("info", qsTr("Design preview"), qsTr("Signing in is connected in Sprint 3."))
                }
            }

            Txt {
                width: parent.width
                text: qsTr("Forgot your password? Ask an administrator to reset it.")
                variant: "caption"
                muted: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
            }
        }
    }
}
