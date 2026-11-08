import QtQuick

// Theme-tinted SVG icon, rendered at the exact device pixel size.
Image {
    id: root

    property string name: ""
    property color color: Theme.colors.text
    property int size: 20

    width: size
    height: size
    sourceSize: Qt.size(Math.ceil(size * Screen.devicePixelRatio),
                        Math.ceil(size * Screen.devicePixelRatio))
    source: name ? "image://icon/" + name + "?color=" + encodeURIComponent(color.toString()) : ""
    fillMode: Image.PreserveAspectFit
    smooth: true
    cache: true
}
