import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// My profile: picture, contact details, licence and password.
Flickable {
    id: page

    property var section: ({})

    contentWidth: width
    contentHeight: column.implicitHeight + Theme.space.xl * 2
    boundsBehavior: Flickable.StopAtBounds
    clip: true
    ScrollBar.vertical: ScrollBar {}

    Connections {
        target: Session
        function onPasswordChanged() {
            current.text = ""; password.text = ""; confirm.text = ""
            Toasts.show("success", qsTr("Password changed"), qsTr("Use it the next time you sign in."))
        }
    }

    ColumnLayout {
        id: column
        x: Theme.space.xl
        y: Theme.space.xl
        width: Math.min(720, page.width - Theme.space.xl * 2)
        spacing: Theme.space.lg

        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: 128
            padding: Theme.space.lg
            Row {
                spacing: Theme.space.lg
                Avatar { size: 80; source: Session.picture; initials: Session.initials }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Txt { text: Session.displayName; variant: "title2" }
                    Txt { text: Session.roleLabel + "  ·  @" + Session.username; muted: true }
                    FileButton {
                        compact: true
                        iconName: "user"
                        text: qsTr("Change picture")
                        busy: Session.busy
                        onChosen: function (url) { Session.uploadPicture(url) }
                    }
                }
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: contact.implicitHeight + Theme.space.lg * 2
            padding: Theme.space.lg
            Column {
                id: contact
                width: parent.width
                spacing: Theme.space.md
                SectionHeader { width: parent.width; title: qsTr("Contact"); description: qsTr("Your employee ID and email are managed by an administrator.") }
                Row {
                    spacing: Theme.space.xl
                    Column { Txt { text: qsTr("Employee ID"); variant: "caption"; muted: true } Txt { text: Session.contact.employeeId || "" } }
                    Column { Txt { text: qsTr("Email"); variant: "caption"; muted: true } Txt { text: Session.contact.email || "" } }
                }
                Row {
                    spacing: Theme.space.xs
                    AppTextField { id: phone; width: 240; label: qsTr("Contact number"); text: Session.contact.phone || "" }
                    AppButton {
                        y: 21
                        text: qsTr("Save")
                        enabled: phone.text !== (Session.contact.phone || "") && !Session.busy
                        onClicked: Session.updatePhone(phone.text)
                    }
                }
            }
        }

        Card {
            visible: Session.licence.number !== undefined
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? licence.implicitHeight + Theme.space.lg * 2 : 0
            padding: Theme.space.lg
            Column {
                id: licence
                width: parent.width
                spacing: Theme.space.sm
                SectionHeader { width: parent.width; title: qsTr("DGCA Remote Pilot Certificate") }
                Row {
                    spacing: Theme.space.md
                    Txt { text: Session.licence.number || ""; variant: "bodyStrong"; anchors.verticalCenter: parent.verticalCenter }
                    StatusPill {
                        anchors.verticalCenter: parent.verticalCenter
                        kind: ({ valid: "success", expiring: "warning", expired: "danger" })[Session.licence.status] || "neutral"
                        text: Session.licence.status === "expired" ? qsTr("Expired %1").arg(Session.licence.expires)
                                                                     : qsTr("Valid to %1").arg(Session.licence.expires)
                    }
                }
                Row {
                    spacing: Theme.space.sm
                    FileButton {
                        compact: true
                        iconName: "plus"
                        text: Session.licence.document ? qsTr("Replace certificate copy") : qsTr("Attach certificate copy")
                        nameFilters: [qsTr("Certificate (*.pdf *.png *.jpg *.jpeg)")]
                        onChosen: function (url) { Session.uploadLicence(url) }
                    }
                    Txt {
                        anchors.verticalCenter: parent.verticalCenter
                        text: Session.licence.document ? qsTr("A copy is attached.") : qsTr("No copy attached yet.")
                        variant: "caption"
                        muted: true
                    }
                }
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: passwordBlock.implicitHeight + Theme.space.lg * 2
            padding: Theme.space.lg
            Column {
                id: passwordBlock
                width: parent.width
                spacing: Theme.space.md
                SectionHeader { width: parent.width; title: qsTr("Password") }
                Row {
                    width: parent.width
                    spacing: Theme.space.md
                    AppTextField { id: current; width: (parent.width - parent.spacing * 2) / 3; label: qsTr("Current password"); password: true }
                    AppTextField { id: password; width: (parent.width - parent.spacing * 2) / 3; label: qsTr("New password"); password: true }
                    AppTextField {
                        id: confirm
                        width: (parent.width - parent.spacing * 2) / 3
                        label: qsTr("Repeat new password")
                        password: true
                        error: text !== "" && text !== password.text ? qsTr("Does not match.") : ""
                    }
                }
                PasswordChecklist { id: checklist; password: password.text; username: Session.username }
                AppButton {
                    text: qsTr("Change password")
                    variant: "primary"
                    enabled: current.text !== "" && checklist.allMet && confirm.text === password.text && !Session.busy
                    onClicked: Session.changePassword(current.text, password.text, confirm.text)
                }
            }
        }

        ErrorBanner { Layout.fillWidth: true; text: Session.error }

        AppButton {
            variant: "ghost"
            iconName: "log-out"
            text: qsTr("Sign out")
            onClicked: Session.signOut()
        }
    }
}
