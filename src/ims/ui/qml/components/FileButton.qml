import QtQuick
import QtQuick.Dialogs

// Button that opens the Windows file picker and reports the chosen file.
AppButton {
    id: root

    property var nameFilters: [qsTr("Images (*.png *.jpg *.jpeg)")]
    property string dialogTitle: qsTr("Choose a file")

    signal chosen(string url)

    onClicked: dialog.open()

    FileDialog {
        id: dialog
        title: root.dialogTitle
        nameFilters: root.nameFilters
        fileMode: FileDialog.OpenFile
        onAccepted: root.chosen(String(selectedFile))
    }
}
