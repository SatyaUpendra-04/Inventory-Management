import QtQuick
import "../components"

// Shows a new temporary password once, so the administrator can hand it over.
Sheet {
    id: sheet

    property string name: ""
    property string username: ""
    property string password: ""

    function show(personName, personUsername, temporary) {
        name = personName
        username = personUsername
        password = temporary
        secret.copied = false
        open()
    }

    title: qsTr("Temporary password for %1").arg(name)
    subtitle: qsTr("Give it to them in person or by phone. They choose their own password when they first sign in. It is shown only once.")
    onClosed: password = ""

    Column {
        width: parent.width
        spacing: Theme.space.sm
        Row {
            spacing: Theme.space.xs
            Txt { text: qsTr("Username"); muted: true }
            Txt { text: sheet.username; variant: "bodyStrong" }
        }
        SecretField { id: secret; value: sheet.password }
    }

    actions: [
        AppButton { variant: "primary"; text: qsTr("Done"); onClicked: sheet.close() }
    ]
}
