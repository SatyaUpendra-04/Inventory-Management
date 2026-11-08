import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects

// macOS-style sheet: slides down from the top of the window over a dimmed background.
Popup {
    id: sheet

    property string title: ""
    property string subtitle: ""
    default property alias content: body.data
    property alias actions: actionRow.data
    property real maxBodyHeight: parent ? parent.height - 220 : 600

    parent: Overlay.overlay
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape
    width: Math.min(520, parent ? parent.width - 64 : 520)
    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: 0
    padding: Theme.space.lg
    topPadding: Theme.space.lg + 4

    Overlay.modal: Rectangle {
        color: Theme.colors.overlay
        Behavior on opacity { NumberAnimation { duration: Theme.motion.standard } }
    }

    enter: Transition {
        NumberAnimation {
            property: "y"
            from: Theme.reducedMotion ? 0 : -sheet.implicitHeight
            to: 0
            duration: Theme.motion.page
            easing.type: Easing.BezierSpline
            easing.bezierCurve: Theme.motion.easing
        }
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.standard }
    }
    exit: Transition {
        NumberAnimation {
            property: "y"
            to: Theme.reducedMotion ? 0 : -sheet.height
            duration: Theme.motion.standard
            easing.type: Easing.InCubic
        }
        NumberAnimation { property: "opacity"; to: 0; duration: Theme.motion.standard }
    }

    background: Item {
        Rectangle {
            id: shadowShape
            anchors.fill: parent
            color: Theme.colors.surfaceRaised
            bottomLeftRadius: Theme.radius.lg
            bottomRightRadius: Theme.radius.lg
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                blurMax: 48
                shadowColor: Theme.colors.shadow
                shadowOpacity: Theme.shadows.high.opacity
                shadowBlur: Theme.shadows.high.blur
                shadowVerticalOffset: Theme.shadows.high.offset
                autoPaddingEnabled: true
            }
        }
        Rectangle {
            anchors.fill: parent
            color: Theme.colors.surfaceRaised
            bottomLeftRadius: Theme.radius.lg
            bottomRightRadius: Theme.radius.lg
            border.width: 1
            border.color: Theme.colors.divider
        }
    }

    contentItem: Column {
        spacing: Theme.space.md

        Column {
            width: parent.width
            spacing: 2
            Txt { text: sheet.title; variant: "title3"; width: parent.width; wrapMode: Text.WordWrap }
            Txt {
                visible: sheet.subtitle !== ""
                text: sheet.subtitle
                muted: true
                width: parent.width
                wrapMode: Text.WordWrap
            }
        }

        // Content scrolls when it is taller than the window allows.
        Flickable {
            id: bodyScroll
            width: parent.width
            height: Math.min(body.implicitHeight, sheet.maxBodyHeight)
            contentWidth: width
            contentHeight: body.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            clip: body.implicitHeight > sheet.maxBodyHeight
            interactive: body.implicitHeight > sheet.maxBodyHeight
            ScrollBar.vertical: ScrollBar { policy: bodyScroll.interactive ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }

            Item {
                id: body
                width: bodyScroll.width - (bodyScroll.interactive ? 12 : 0)
                implicitHeight: childrenRect.height
                height: implicitHeight
            }
        }

        Row {
            id: actionRow
            anchors.right: parent.right
            spacing: Theme.space.xs
        }
    }
}
