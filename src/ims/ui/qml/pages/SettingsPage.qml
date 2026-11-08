import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

Flickable {
    id: page

    property var section: ({})
    property string customAccent: Theme.accent

    function change(fn) { ApplicationWindow.window.transitionTheme(fn) }

    contentWidth: width
    contentHeight: column.implicitHeight + Theme.space.xl * 2
    boundsBehavior: Flickable.StopAtBounds
    clip: true
    ScrollBar.vertical: ScrollBar {}

    ColumnLayout {
        id: column
        x: Theme.space.xl
        y: Theme.space.xl
        width: Math.min(760, page.width - Theme.space.xl * 2)
        spacing: Theme.space.lg

        // ---------------------------------------------------------- appearance
        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: appearance.implicitHeight + Theme.space.lg * 2
            padding: Theme.space.lg

            ColumnLayout {
                id: appearance
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: Theme.space.md

                SectionHeader {
                    Layout.fillWidth: true
                    title: qsTr("Appearance")
                    description: qsTr("Choose light or dark, or follow your Windows setting.")
                }

                Row {
                    spacing: Theme.space.md
                    Repeater {
                        model: [
                            { value: "system", label: qsTr("Automatic"), icon: "monitor" },
                            { value: "light", label: qsTr("Light"), icon: "sun" },
                            { value: "dark", label: qsTr("Dark"), icon: "moon" }
                        ]
                        delegate: AbstractButton {
                            id: tile
                            required property var modelData
                            readonly property bool chosen: Theme.mode === modelData.value
                            width: 150
                            height: 128
                            hoverEnabled: true
                            focusPolicy: Qt.StrongFocus
                            Accessible.name: modelData.label
                            onClicked: page.change(function () { Theme.setMode(tile.modelData.value) })

                            contentItem: Column {
                                spacing: Theme.space.xs
                                ThemeThumbnail {
                                    width: tile.width
                                    height: 92
                                    mode: tile.modelData.value
                                    chosen: tile.chosen
                                    hovered: tile.hovered
                                    FocusRing { show: tile.visualFocus; baseRadius: Theme.radius.md }
                                }
                                Row {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    spacing: 6
                                    Icon { name: tile.modelData.icon; size: 15; color: tile.chosen ? Theme.colors.accentText : Theme.colors.textMuted }
                                    Txt {
                                        text: tile.modelData.label
                                        variant: "caption"
                                        font.weight: tile.chosen ? Theme.type.semibold : Theme.type.medium
                                        color: tile.chosen ? Theme.colors.accentText : Theme.colors.text
                                    }
                                }
                            }
                            background: Item {}
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.colors.divider }

                SectionHeader {
                    Layout.fillWidth: true
                    title: qsTr("Accent colour")
                    description: qsTr("Used for buttons, selection and focus — about a tenth of the screen.")
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.space.sm
                    Repeater {
                        model: Theme.presets
                        delegate: AbstractButton {
                            id: swatch
                            required property var modelData
                            readonly property bool chosen: Theme.accent.toLowerCase() === modelData.color.toLowerCase()
                            width: 30
                            height: 30
                            hoverEnabled: true
                            focusPolicy: Qt.StrongFocus
                            Accessible.name: modelData.name
                            ToolTip.visible: hovered
                            ToolTip.delay: 400
                            ToolTip.text: modelData.name
                            onClicked: page.change(function () { Theme.setAccent(swatch.modelData.color) })
                            scale: down ? 0.92 : (hovered ? 1.08 : 1)
                            Behavior on scale { NumberAnimation { duration: Theme.motion.micro; easing.type: Easing.OutBack } }

                            background: Rectangle {
                                radius: 15
                                color: swatch.modelData.color
                                border.width: 1
                                border.color: Qt.rgba(0, 0, 0, 0.12)
                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: -4
                                    radius: 19
                                    color: "transparent"
                                    border.width: 2
                                    border.color: swatch.chosen || swatch.visualFocus ? Theme.colors.focusRing : "transparent"
                                }
                                Icon {
                                    anchors.centerIn: parent
                                    visible: swatch.chosen
                                    name: "check"
                                    size: 16
                                    color: "#ffffff"
                                }
                            }
                        }
                    }
                }

                Row {
                    spacing: Theme.space.xs
                    AppTextField {
                        id: hexField
                        width: 160
                        label: qsTr("Custom colour")
                        placeholder: "#2f6fed"
                        text: page.customAccent
                        iconName: "palette"
                        error: Theme.accentProblems(text).join(" ")
                        helper: Theme.accentIsAdjusted(text) ? qsTr("Adjusted slightly to keep text readable.") : ""
                        onAccepted: applyAccent.clicked()
                    }
                    AppButton {
                        id: applyAccent
                        y: 21
                        text: qsTr("Apply")
                        enabled: Theme.accentProblems(hexField.text).length === 0
                        onClicked: page.change(function () { Theme.setAccent(hexField.text) })
                    }
                }
            }
        }

        // ---------------------------------------------------------- accessibility
        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: access.implicitHeight + Theme.space.lg * 2
            padding: Theme.space.lg

            ColumnLayout {
                id: access
                anchors.left: parent.left
                anchors.right: parent.right
                spacing: Theme.space.md

                SectionHeader {
                    Layout.fillWidth: true
                    title: qsTr("Accessibility")
                    description: qsTr("Every theme meets WCAG 2.2 AA contrast. These options go further.")
                }

                RowLayout {
                    Layout.fillWidth: true
                    Column {
                        Layout.fillWidth: true
                        Txt { text: qsTr("Increase contrast"); variant: "bodyStrong" }
                        Txt {
                            width: parent.width
                            text: qsTr("Pure black and white surfaces with stronger borders, for bright sites and outdoor use.")
                            muted: true
                            wrapMode: Text.WordWrap
                        }
                    }
                    AppToggle {
                        checked: Theme.highContrast
                        Accessible.name: qsTr("Increase contrast")
                        onToggled: { var on = checked; page.change(function () { Theme.setHighContrast(on) }) }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.colors.divider }

                RowLayout {
                    Layout.fillWidth: true
                    Column {
                        Layout.fillWidth: true
                        Txt { text: qsTr("Reduce motion"); variant: "bodyStrong" }
                        Txt {
                            width: parent.width
                            text: Theme.systemReducesMotion
                                  ? qsTr("Windows animation effects are off, so movement is already replaced with simple fades.")
                                  : qsTr("Replace sliding and springing animations with simple fades.")
                            muted: true
                            wrapMode: Text.WordWrap
                        }
                    }
                    AppToggle {
                        checked: Theme.reduceMotionSetting || Theme.systemReducesMotion
                        enabled: !Theme.systemReducesMotion
                        Accessible.name: qsTr("Reduce motion")
                        onToggled: Theme.setReduceMotion(checked)
                    }
                }
            }
        }

        // ---------------------------------------------------------- about
        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: about.implicitHeight + Theme.space.lg * 2
            padding: Theme.space.lg

            Column {
                id: about
                width: parent.width
                spacing: 4
                SectionHeader { width: parent.width; title: qsTr("About") }
                Txt { text: qsTr("Inventory Management %1 · %2").arg(AppVersion).arg(AppEnvironment); muted: true }
                Txt { text: qsTr("Keyboard: Ctrl+, opens Settings · Ctrl+Shift+L switches light and dark"); muted: true; variant: "caption" }
            }
        }
    }
}
