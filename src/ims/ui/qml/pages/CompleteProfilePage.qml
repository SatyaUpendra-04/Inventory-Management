import QtQuick
import "../components"

// Every person needs a profile picture before starting.
GateFrame {
    id: page

    title: qsTr("Add your profile picture")
    subtitle: qsTr("Your picture helps the team see who has which equipment.")
    cardWidth: 420

    Avatar {
        anchors.horizontalCenter: parent.horizontalCenter
        size: 112
        source: Session.picture
        initials: Session.initials
    }
    FileButton {
        anchors.horizontalCenter: parent.horizontalCenter
        text: Session.picture ? qsTr("Choose a different picture") : qsTr("Choose picture")
        iconName: "user"
        busy: Session.busy
        dialogTitle: qsTr("Choose your profile picture")
        onChosen: function (url) { Session.uploadPicture(url) }
    }
    Txt {
        width: parent.width
        text: qsTr("PNG or JPEG, up to 5 MB. It is cropped to a square.")
        variant: "caption"
        muted: true
        horizontalAlignment: Text.AlignHCenter
    }
    ErrorBanner { text: Session.error }
    AppButton {
        width: parent.width
        variant: "primary"
        text: qsTr("Continue")
        enabled: Session.picture !== "" && !Session.busy
        onClicked: Session.finishProfile()
    }
    AppButton {
        width: parent.width
        variant: "ghost"
        text: qsTr("Sign out")
        onClicked: Session.signOut()
    }
}
