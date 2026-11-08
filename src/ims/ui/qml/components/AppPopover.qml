import QtQuick
import QtQuick.Controls.Basic

// Small floating panel anchored to the control that opened it.
Popup {
    id: popover

    default property alias content: body.data

    padding: Theme.space.md
    transformOrigin: Item.Top
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.micro }
        NumberAnimation {
            property: "scale"; from: Theme.reducedMotion ? 1 : 0.94; to: 1
            duration: Theme.motion.standard; easing.type: Easing.OutBack; easing.overshoot: 1.1
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; to: 0; duration: Theme.motion.micro }
        NumberAnimation { property: "scale"; to: Theme.reducedMotion ? 1 : 0.97; duration: Theme.motion.micro }
    }

    background: Card { elevation: "medium"; radius: Theme.radius.md; fill: Theme.colors.surfaceRaised }

    contentItem: Item {
        id: body
        implicitWidth: childrenRect.width
        implicitHeight: childrenRect.height
    }
}
