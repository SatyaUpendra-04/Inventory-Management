import QtQuick

// Text in one of the type-scale styles. Never set font sizes by hand in screens.
Text {
    id: root

    // caption | body | bodyStrong | headline | title3 | title2 | title1
    property string variant: "body"
    property bool muted: false

    readonly property bool _display: variant.indexOf("title") === 0

    color: muted ? Theme.colors.textMuted : Theme.colors.text
    font.family: _display ? Theme.type.displayFamily : Theme.type.family
    font.pixelSize: {
        switch (variant) {
        case "caption": return Theme.type.caption
        case "headline": return Theme.type.headline
        case "title3": return Theme.type.title3
        case "title2": return Theme.type.title2
        case "title1": return Theme.type.title1
        default: return Theme.type.body
        }
    }
    font.weight: (variant === "body" || variant === "caption") ? Theme.type.regular : Theme.type.semibold
    font.letterSpacing: _display ? -0.2 : 0
    verticalAlignment: Text.AlignVCenter
}
