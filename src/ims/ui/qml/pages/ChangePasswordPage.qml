import QtQuick
import "../components"

// Replace the temporary password before using the app.
GateFrame {
    id: page

    title: qsTr("Choose your password")
    subtitle: qsTr("Hi %1. Replace the temporary password you were given with one only you know.").arg(Session.firstName)
    cardWidth: 440

    function submit() { Session.changePassword(current.text, password.text, confirm.text) }

    AppTextField {
        id: current
        width: parent.width
        label: qsTr("Temporary password")
        password: true
        field.focus: true
        onAccepted: password.field.forceActiveFocus()
    }
    AppTextField { id: password; width: parent.width; label: qsTr("New password"); password: true }
    AppTextField {
        id: confirm
        width: parent.width
        label: qsTr("Repeat new password")
        password: true
        error: text !== "" && text !== password.text ? qsTr("The passwords do not match.") : ""
        onAccepted: page.submit()
    }
    PasswordChecklist { id: checklist; password: password.text; username: Session.username }
    ErrorBanner { text: Session.error }
    AppButton {
        width: parent.width
        variant: "primary"
        text: qsTr("Save password")
        busy: Session.busy
        enabled: !Session.busy && current.text !== "" && checklist.allMet && confirm.text === password.text
        onClicked: page.submit()
    }
    AppButton {
        width: parent.width
        variant: "ghost"
        text: qsTr("Sign out")
        onClicked: Session.signOut()
    }
}
