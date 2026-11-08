import QtQuick

// Loading placeholder with a soft shimmer (static when motion is reduced).
Rectangle {
    id: root

    radius: Theme.radius.sm
    color: Theme.colors.element
    clip: true

    Rectangle {
        id: shine
        visible: !Theme.reducedMotion
        width: root.width * 0.6
        height: root.height
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "transparent" }
            GradientStop { position: 0.5; color: Theme.colors.elementHover }
            GradientStop { position: 1.0; color: "transparent" }
        }
        NumberAnimation on x {
            running: shine.visible
            from: -shine.width
            to: root.width
            duration: 1300
            loops: Animation.Infinite
            easing.type: Easing.InOutSine
        }
    }
}
