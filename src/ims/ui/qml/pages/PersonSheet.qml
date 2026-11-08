import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Add or edit a person, and manage their account.
Sheet {
    id: sheet

    property bool isNew: true
    property var person: ({})
    property bool confirmingRemove: false

    width: Math.min(600, parent ? parent.width - 64 : 600)
    title: isNew ? qsTr("Add person") : person.name || ""
    subtitle: isNew ? qsTr("They will get a temporary password and choose their own when they first sign in.")
                    : qsTr("@%1 · %2").arg(person.username || "").arg(person.accountLabel || "")

    function openNew() {
        isNew = true
        person = ({})
        reset()
        open()
    }
    function openEdit(personId) {
        isNew = false
        person = People.person(personId)
        reset()
        open()
    }
    function reset() {
        People.clearError()
        confirmingRemove = false
        fullName.text = person.name || ""
        username.text = person.username || ""
        employeeId.text = person.employeeId || ""
        email.text = person.email || ""
        phone.text = person.phone || ""
        role.selectValue(person.role || "surveyor")
        licenceNumber.text = person.licenceNumber || ""
        if (person.licenceExpiryIso) {
            expiry.selectedDate = new Date(person.licenceExpiryIso + "T00:00:00")
            expiry.hasDate = true
        } else {
            expiry.hasDate = false
        }
    }
    function values() {
        return {
            fullName: fullName.text, username: username.text, employeeId: employeeId.text,
            email: email.text, phone: phone.text, role: role.currentValue,
            licenceNumber: licenceNumber.text,
            licenceExpiry: expiry.hasDate ? Qt.formatDate(expiry.selectedDate, "yyyy-MM-dd") : ""
        }
    }
    function save() {
        if (isNew) People.onboard(values())
        else People.update(person.personId, person.version, values())
    }

    Connections {
        target: People
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md

        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: fullName; width: (parent.width - parent.spacing) / 2; label: qsTr("Full name") }
            AppTextField { id: username; width: (parent.width - parent.spacing) / 2; label: qsTr("Username"); placeholder: qsTr("e.g. skumar") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: employeeId; width: (parent.width - parent.spacing) / 2; label: qsTr("Employee ID") }
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Txt { text: qsTr("Role"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect {
                    id: role
                    width: parent.width
                    model: People.roles()
                    textRole: "label"
                    valueRole: "value"
                    enabled: !sheet.person.isSelf
                }
            }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: email; width: (parent.width - parent.spacing) / 2; label: qsTr("Work email") }
            AppTextField { id: phone; width: (parent.width - parent.spacing) / 2; label: qsTr("Contact number") }
        }

        Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }

        Column {
            width: parent.width
            spacing: 2
            Txt { text: qsTr("DGCA Remote Pilot Certificate"); variant: "bodyStrong" }
            Txt {
                text: role.currentValue === "pilot" ? qsTr("Required for pilots.") : qsTr("Optional for this role.")
                variant: "caption"
                muted: true
            }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: licenceNumber; width: (parent.width - parent.spacing) / 2; label: qsTr("Certificate number") }
            AppDatePicker { id: expiry; width: (parent.width - parent.spacing) / 2; label: qsTr("Valid until") }
        }
        Row {
            visible: !sheet.isNew && sheet.person.licenceNumber !== ""
            spacing: Theme.space.sm
            FileButton {
                compact: true
                iconName: "plus"
                text: sheet.person.licenceDocument ? qsTr("Replace certificate copy") : qsTr("Attach certificate copy")
                nameFilters: [qsTr("Certificate (*.pdf *.png *.jpg *.jpeg)")]
                onChosen: function (url) { People.uploadLicence(sheet.person.personId, url) }
            }
            Txt {
                anchors.verticalCenter: parent.verticalCenter
                text: sheet.person.licenceDocument ? qsTr("A copy is attached.") : qsTr("No copy attached yet.")
                variant: "caption"
                muted: true
            }
        }

        // ------------------------------------------------------------ account actions
        Column {
            visible: !sheet.isNew && !sheet.person.isSelf
            width: parent.width
            spacing: Theme.space.sm
            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Txt { text: qsTr("Account"); variant: "bodyStrong" }
            Flow {
                width: parent.width
                spacing: Theme.space.xs
                AppButton { compact: true; iconName: "lock"; text: qsTr("Reset password"); onClicked: People.resetPassword(sheet.person.personId) }
                AppButton {
                    compact: true
                    visible: sheet.person.account === "danger"
                    iconName: "refresh"
                    text: qsTr("Unlock")
                    onClicked: People.unlock(sheet.person.personId)
                }
                AppButton {
                    compact: true
                    iconName: sheet.person.account === "neutral" ? "check" : "circle-minus"
                    text: sheet.person.account === "neutral" ? qsTr("Reactivate") : qsTr("Deactivate")
                    onClicked: People.setActive(sheet.person.personId, sheet.person.version, sheet.person.account === "neutral")
                }
                AppButton {
                    compact: true
                    variant: "ghost"
                    iconName: "x"
                    text: qsTr("Remove…")
                    onClicked: sheet.confirmingRemove = true
                }
            }
            Rectangle {
                visible: sheet.confirmingRemove
                width: parent.width
                height: removeRow.implicitHeight + Theme.space.sm * 2
                radius: Theme.radius.sm
                color: Theme.colors.dangerBg
                border.width: 1
                border.color: Theme.colors.dangerBorder
                Row {
                    id: removeRow
                    x: Theme.space.sm
                    y: Theme.space.sm
                    width: parent.width - Theme.space.sm * 2
                    spacing: Theme.space.sm
                    Txt {
                        width: parent.width - removeButton.width - cancelRemove.width - Theme.space.sm * 2
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Remove %1? They can no longer sign in, but their history is kept.").arg(sheet.person.name)
                        color: Theme.colors.dangerText
                        wrapMode: Text.WordWrap
                    }
                    AppButton { id: cancelRemove; compact: true; text: qsTr("Keep"); onClicked: sheet.confirmingRemove = false }
                    AppButton {
                        id: removeButton
                        compact: true
                        variant: "danger"
                        text: qsTr("Remove")
                        onClicked: People.remove(sheet.person.personId, sheet.person.version)
                    }
                }
            }
        }

        ErrorBanner { text: People.error }
    }

    actions: [
        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
        AppButton {
            variant: "primary"
            text: sheet.isNew ? qsTr("Add person") : qsTr("Save changes")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: sheet.save()
        }
    ]
}
