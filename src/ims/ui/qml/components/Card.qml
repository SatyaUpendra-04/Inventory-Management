import QtQuick
import QtQuick.Effects

// Raised surface. The shadow is drawn from a separate copy of the shape, so the
// content itself is never rendered through an effect (text stays sharp).
Item {
    id: root

    property string elevation: "low"  // none | low | medium | high
    property real radius: Theme.radius.lg
    property color fill: Theme.colors.surface
    property bool outlined: true
    property int padding: 0
    default property alias content: body.data

    Rectangle {
        id: shadowShape
        anchors.fill: parent
        radius: root.radius
        color: root.fill
        visible: root.elevation !== "none"
        layer.enabled: visible
        layer.effect: MultiEffect {
            shadowEnabled: true
            blurMax: 48
            shadowColor: Theme.colors.shadow
            shadowOpacity: root.elevation !== "none" ? Theme.shadows[root.elevation].opacity : 0
            shadowBlur: root.elevation !== "none" ? Theme.shadows[root.elevation].blur : 0
            shadowVerticalOffset: root.elevation !== "none" ? Theme.shadows[root.elevation].offset : 0
            shadowHorizontalOffset: 0
            autoPaddingEnabled: true
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: root.radius
        color: root.fill
        border.width: root.outlined ? 1 : 0
        border.color: Theme.colors.divider
    }

    Item {
        id: body
        anchors.fill: parent
        anchors.margins: root.padding
    }
}
