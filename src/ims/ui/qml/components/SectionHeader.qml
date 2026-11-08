import QtQuick

// Title + description at the top of a content block.
Column {
    id: root

    property string title: ""
    property string description: ""

    spacing: 2

    Txt { text: root.title; variant: "headline" }
    Txt {
        visible: root.description !== ""
        text: root.description
        muted: true
        width: root.width
        wrapMode: Text.WordWrap
    }
}
