import QtQuick
import "../components"

// First run: create the first administrator.
GateFrame {
    id: page

    title: qsTr("Set up Inventory Management")
    subtitle: qsTr("Create the first administrator account. You can add everyone else afterwards.")
    cardWidth: 520

    function submit() {
        Session.setupAdmin({
            fullName: fullName.text, username: username.text, employeeId: employeeId.text,
            email: email.text, phone: phone.text
        }, password.text, confirm.text)
    }

    Row {
        width: parent.width
        spacing: Theme.space.md
        AppTextField { id: fullName; width: (parent.width - parent.spacing) / 2; label: qsTr("Full name"); field.focus: true }
        AppTextField { id: username; width: (parent.width - parent.spacing) / 2; label: qsTr("Username"); placeholder: qsTr("e.g. skumar") }
    }
    Row {
        width: parent.width
        spacing: Theme.space.md
        AppTextField { id: employeeId; width: (parent.width - parent.spacing) / 2; label: qsTr("Employee ID") }
        AppTextField { id: phone; width: (parent.width - parent.spacing) / 2; label: qsTr("Contact number") }
    }
    AppTextField { id: email; width: parent.width; label: qsTr("Work email") }
    Row {
        width: parent.width
        spacing: Theme.space.md
        AppTextField { id: password; width: (parent.width - parent.spacing) / 2; label: qsTr("Password"); password: true }
        AppTextField {
            id: confirm
            width: (parent.width - parent.spacing) / 2
            label: qsTr("Repeat password")
            password: true
            error: text !== "" && text !== password.text ? qsTr("The passwords do not match.") : ""
            onAccepted: page.submit()
        }
    }
    PasswordChecklist { id: checklist; password: password.text; username: username.text }
    ErrorBanner { text: Session.error }
    AppButton {
        width: parent.width
        variant: "primary"
        text: qsTr("Create administrator")
        busy: Session.busy
        enabled: !Session.busy && checklist.allMet && confirm.text === password.text
        onClicked: page.submit()
    }
}
