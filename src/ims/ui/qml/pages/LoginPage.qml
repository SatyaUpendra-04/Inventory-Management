import QtQuick
import "../components"

// Sign in.
GateFrame {
    id: page

    title: qsTr("Sign in")
    subtitle: qsTr("Inventory Management")

    function submit() { Session.signIn(username.text, password.text) }

    AppTextField {
        id: username
        width: parent.width
        label: qsTr("Username")
        placeholder: qsTr("e.g. skumar")
        iconName: "user"
        field.focus: true
        onAccepted: password.field.forceActiveFocus()
    }
    AppTextField {
        id: password
        width: parent.width
        label: qsTr("Password")
        placeholder: qsTr("Your password")
        iconName: "lock"
        password: true
        onAccepted: page.submit()
    }
    ErrorBanner { text: Session.error }
    AppButton {
        id: signInButton
        width: parent.width
        variant: "primary"
        text: qsTr("Sign in")
        busy: Session.busy
        enabled: !Session.busy
        onClicked: page.submit()
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
