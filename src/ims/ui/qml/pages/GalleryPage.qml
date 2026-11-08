import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// Every component in its states, for review and screenshot tests.
Flickable {
    id: page

    property var section: ({})
    property bool loading: false

    contentWidth: width
    contentHeight: column.implicitHeight + Theme.space.xl * 2
    boundsBehavior: Flickable.StopAtBounds
    clip: true
    ScrollBar.vertical: ScrollBar {}

    component Block: Card {
        id: block
        property string title: ""
        property string description: ""
        default property alias body: inner.data
        Layout.fillWidth: true
        Layout.preferredHeight: blockColumn.implicitHeight + Theme.space.lg * 2
        padding: Theme.space.lg
        Column {
            id: blockColumn
            width: parent.width
            spacing: Theme.space.md
            SectionHeader { width: parent.width; title: block.title; description: block.description }
            Item {
                id: inner
                width: parent.width
                implicitHeight: childrenRect.height
                height: implicitHeight
            }
        }
    }

    component Swatch: Rectangle {
        property string label: ""
        width: 52
        height: 40
        radius: Theme.radius.sm
        border.width: 1
        border.color: Theme.colors.divider
        Txt { anchors.bottom: parent.bottom; anchors.bottomMargin: -16; anchors.horizontalCenter: parent.horizontalCenter
              text: parent.label; variant: "caption"; muted: true; font.pixelSize: 10 }
    }

    ColumnLayout {
        id: column
        x: Theme.space.xl
        y: Theme.space.xl
        width: page.width - Theme.space.xl * 2
        spacing: Theme.space.lg

        // ------------------------------------------------------------------ colour
        Block {
            title: qsTr("Colour")
            description: qsTr("Generated in OKLCH, so each step is an even visual change. Proportions follow 60-30-10: neutral surfaces, content, then accent.")

            Column {
                width: parent.width
                spacing: Theme.space.lg

                Row {
                    width: parent.width
                    height: 34
                    Rectangle { width: parent.width * 0.6; height: parent.height; color: Theme.colors.window; border.width: 1; border.color: Theme.colors.divider
                                Txt { anchors.centerIn: parent; text: "60%  surfaces"; variant: "caption"; muted: true } }
                    Rectangle { width: parent.width * 0.3; height: parent.height; color: Theme.colors.elementHover
                                Txt { anchors.centerIn: parent; text: "30%  content"; variant: "caption" } }
                    Rectangle { width: parent.width * 0.1; height: parent.height; color: Theme.colors.accent
                                Txt { anchors.centerIn: parent; text: "10%"; variant: "caption"; color: Theme.colors.onAccent } }
                }

                Repeater {
                    model: ["accent", "neutral", "success", "warning", "danger", "info"]
                    delegate: Row {
                        required property string modelData
                        spacing: 6
                        height: 58
                        Txt { width: 70; text: modelData; variant: "caption"; muted: true; height: 40 }
                        Repeater {
                            model: Theme.palettes[modelData]
                            delegate: Swatch {
                                required property string modelData
                                required property int index
                                color: modelData
                                label: index + 1
                            }
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------------------ type
        Block {
            title: qsTr("Typography")
            description: qsTr("%1 on a 1.2 modular scale.").arg(Theme.type.family)
            Column {
                spacing: Theme.space.xs
                Txt { text: qsTr("Fleet overview"); variant: "title1" }
                Txt { text: qsTr("Projects this quarter"); variant: "title2" }
                Txt { text: qsTr("DRN-0002 needs service"); variant: "title3" }
                Txt { text: qsTr("Section heading"); variant: "headline" }
                Txt { text: qsTr("Strong body text for labels and emphasis"); variant: "bodyStrong" }
                Txt { text: qsTr("Body text: battery BAT-0121 has 312 cycles and 84% health.") }
                Txt { text: qsTr("Muted text for secondary information"); muted: true }
                Txt { text: qsTr("Caption · last updated 2 minutes ago"); variant: "caption"; muted: true }
            }
        }

        // ------------------------------------------------------------------ buttons
        Block {
            title: qsTr("Buttons")
            description: qsTr("Hover lifts, press sinks. Tab through them to see the focus ring.")
            Column {
                spacing: Theme.space.md
                Row {
                    spacing: Theme.space.xs
                    AppButton { text: qsTr("Deploy kit"); variant: "primary"; iconName: "send" }
                    AppButton { text: qsTr("Reserve"); variant: "secondary"; iconName: "calendar" }
                    AppButton { text: qsTr("Details"); variant: "ghost" }
                    AppButton { text: qsTr("Ground drone"); variant: "danger"; iconName: "alert" }
                    AppButton { text: qsTr("Disabled"); variant: "primary"; enabled: false }
                }
                Row {
                    spacing: Theme.space.xs
                    AppButton { text: qsTr("Small primary"); variant: "primary"; compact: true }
                    AppButton { text: qsTr("Small"); compact: true; iconName: "plus" }
                    AppButton { iconName: "refresh"; compact: true; Accessible.name: qsTr("Refresh") }
                    IconButton { iconName: "search"; tip: qsTr("Search") }
                    IconButton { iconName: "bell"; tip: qsTr("Alerts"); Badge { count: 5; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: -2 } }
                    IconButton { iconName: "more"; tip: qsTr("More"); selected: true }
                }
            }
        }

        // ------------------------------------------------------------------ inputs
        Block {
            title: qsTr("Inputs")
            description: qsTr("Labels above, errors below with an icon, never colour alone.")
            Flow {
                width: parent.width
                spacing: Theme.space.lg
                AppTextField { label: qsTr("Asset tag"); placeholder: "DRN-0001"; iconName: "box" }
                AppTextField { label: qsTr("Serial number"); text: "X8-22"; error: qsTr("Serial number X8-22 is already registered (asset DRN-0001).") }
                AppTextField { label: qsTr("Password"); password: true; text: "Field-Survey-2026!"; helper: qsTr("At least 12 characters.") }
                Column {
                    spacing: 6
                    Txt { text: qsTr("Item type"); variant: "caption"; font.weight: Theme.type.medium }
                    AppSelect { model: ["Drone airframe", "Drone flight battery", "DGPS receiver", "PPK base station", "Tripod", "GCP banner"] }
                }
                AppDatePicker { label: qsTr("Expected return") }
            }
        }

        // ------------------------------------------------------------------ selection
        Block {
            title: qsTr("Selection")
            description: qsTr("Toggles slide; the segmented thumb glides on a spring.")
            Row {
                spacing: Theme.space.xl
                Column {
                    spacing: Theme.space.sm
                    AppToggle { text: qsTr("Notify when service is due"); checked: true }
                    AppToggle { text: qsTr("Include retired equipment") }
                    AppToggle { text: qsTr("Disabled"); enabled: false }
                }
                Column {
                    spacing: Theme.space.sm
                    AppCheckBox { text: qsTr("Drone airframe"); checked: true }
                    AppCheckBox { text: qsTr("Batteries ×4") }
                    AppCheckBox { text: qsTr("SD cards ×2"); checked: true }
                }
                SegmentedControl {
                    id: seg
                    value: "week"
                    options: [{ value: "day", label: qsTr("Day") }, { value: "week", label: qsTr("Week") },
                              { value: "month", label: qsTr("Month") }, { value: "year", label: qsTr("Year") }]
                    segmentWidth: 76
                    onActivated: function (v) { seg.value = v }
                }
            }
        }

        // ------------------------------------------------------------------ status
        Block {
            title: qsTr("Status")
            description: qsTr("Each status has an icon and words as well as a colour.")
            Flow {
                width: parent.width
                spacing: Theme.space.xs
                StatusPill { kind: "success"; text: qsTr("Serviceable") }
                StatusPill { kind: "warning"; text: qsTr("Service due in 6 h") }
                StatusPill { kind: "danger"; text: qsTr("Grounded") }
                StatusPill { kind: "info"; text: qsTr("Reserved for PRJ-114") }
                StatusPill { kind: "neutral"; text: qsTr("Retired") }
            }
        }

        // ------------------------------------------------------------------ elevation
        Block {
            title: qsTr("Surfaces")
            description: qsTr("Three elevation levels; shadows are softer in light mode and deeper in dark mode.")
            Row {
                spacing: Theme.space.lg
                Repeater {
                    model: ["low", "medium", "high"]
                    delegate: Card {
                        id: level
                        required property string modelData
                        width: 180
                        height: 96
                        elevation: modelData
                        Txt { anchors.centerIn: parent; text: level.modelData; variant: "bodyStrong"; muted: true }
                    }
                }
            }
        }

        // ------------------------------------------------------------------ table
        Block {
            title: qsTr("Data table")
            description: qsTr("Click a column heading to sort. Sample data only.")
            DataTable {
                width: parent.width
                height: 36 + 42 * 6 + 2
                model: SampleTable
                rightAligned: [5]
                columnWidths: [120, 200, 150, 210, 140, Math.max(90, width - 822)]
            }
        }

        // ------------------------------------------------------------------ feedback
        Block {
            title: qsTr("Feedback and motion")
            description: qsTr("Toasts slide in, sheets drop from the top, popovers spring open, lists animate changes.")
            Column {
                width: parent.width
                spacing: Theme.space.md

                Flow {
                    width: parent.width
                    spacing: Theme.space.xs
                    AppButton { text: qsTr("Success toast"); compact: true; onClicked: Toasts.show("success", qsTr("Kit deployed"), qsTr("DRN-0001 and 4 batteries are now with PRJ-114.")) }
                    AppButton { text: qsTr("Warning toast"); compact: true; onClicked: Toasts.show("warning", qsTr("Service due soon"), qsTr("DRN-0002 has 6 flight hours left before its 50 h service.")) }
                    AppButton { text: qsTr("Error toast"); compact: true; onClicked: Toasts.show("danger", qsTr("Could not deploy"), qsTr("DRN-0003 is grounded.")) }
                    AppButton { text: qsTr("Info toast"); compact: true; onClicked: Toasts.show("info", qsTr("Saved"), "") }
                    AppButton { text: qsTr("Open sheet"); compact: true; variant: "primary"; onClicked: sheet.open() }
                    AppButton { id: popButton; text: qsTr("Open popover"); compact: true; onClicked: popover.open() }
                    AppButton { text: page.loading ? qsTr("Show content") : qsTr("Show loading"); compact: true; onClicked: page.loading = !page.loading }
                    AppButton { text: qsTr("Preview sign-in screen"); compact: true; iconName: "lock"; onClicked: ApplicationWindow.window.openSignInPreview() }
                }

                AppPopover {
                    id: popover
                    parent: popButton
                    y: popButton.height + 6
                    width: 260
                    Column {
                        width: 228
                        spacing: Theme.space.xs
                        Txt { text: qsTr("DRN-0002"); variant: "bodyStrong" }
                        Txt { text: qsTr("6.0 h until its 50 h service. Last serviced 14 Oct 2026."); muted: true; wrapMode: Text.WordWrap; width: parent.width }
                        StatusPill { kind: "warning"; text: qsTr("Service due soon") }
                    }
                }

                Sheet {
                    id: sheet
                    title: qsTr("Ground DRN-0002?")
                    subtitle: qsTr("Grounded equipment cannot be deployed until an administrator returns it to service.")
                    AppTextField { width: parent.width; label: qsTr("Reason"); placeholder: qsTr("e.g. Motor 3 vibration after landing") }
                    actions: [
                        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
                        AppButton { text: qsTr("Ground drone"); variant: "danger"; onClicked: { sheet.close(); Toasts.show("warning", qsTr("DRN-0002 grounded"), qsTr("Reported for review.")) } }
                    ]
                }

                Row {
                    spacing: Theme.space.md
                    Repeater {
                        model: 3
                        delegate: Card {
                            width: 220
                            height: 92
                            padding: Theme.space.md
                            Column {
                                visible: !page.loading
                                spacing: 4
                                Txt { text: ["DRN-0001", "BAT-0114", "GNS-0004"][index]; variant: "bodyStrong" }
                                Txt { text: ["412.5 flight hours", "182 cycles · 91%", "Calibrated 12 Aug"][index]; muted: true }
                            }
                            Column {
                                visible: page.loading
                                spacing: 8
                                Skeleton { width: 120; height: 14 }
                                Skeleton { width: 170; height: 12 }
                                Skeleton { width: 80; height: 12 }
                            }
                        }
                    }
                }

                Row {
                    spacing: Theme.space.lg
                    Column {
                        spacing: Theme.space.xs
                        Row {
                            spacing: Theme.space.xs
                            AppButton { text: qsTr("Add row"); compact: true; iconName: "plus"; onClicked: rows.insert(0, { label: "BAT-0" + (130 + rows.count) }) }
                            AppButton { text: qsTr("Remove row"); compact: true; iconName: "minus"; enabled: rows.count > 0; onClicked: rows.remove(0) }
                        }
                        ListView {
                            width: 260
                            height: 170
                            clip: true
                            interactive: false
                            spacing: 4
                            model: ListModel { id: rows; ListElement { label: "BAT-0114" } ListElement { label: "BAT-0121" } }
                            add: Transition {
                                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.standard }
                                NumberAnimation { property: "scale"; from: Theme.reducedMotion ? 1 : 0.92; to: 1; duration: Theme.motion.standard; easing.type: Easing.OutBack }
                            }
                            remove: Transition { NumberAnimation { property: "opacity"; to: 0; duration: Theme.motion.standard } }
                            displaced: Transition { NumberAnimation { property: "y"; duration: Theme.motion.standard; easing.type: Easing.OutCubic } }
                            delegate: Rectangle {
                                required property string label
                                width: 260
                                height: 32
                                radius: Theme.radius.sm
                                color: Theme.colors.element
                                Row {
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: Theme.space.sm
                                    spacing: Theme.space.xs
                                    Icon { name: "battery"; size: 16; color: Theme.colors.textMuted; anchors.verticalCenter: parent.verticalCenter }
                                    Txt { text: label; anchors.verticalCenter: parent.verticalCenter }
                                }
                            }
                        }
                    }
                    Card {
                        width: 420
                        height: emptyDemo.implicitHeight + Theme.space.xl * 2
                        EmptyState {
                            id: emptyDemo
                            anchors.centerIn: parent
                            width: 360
                            iconName: "inbox"
                            title: qsTr("No reservations yet")
                            message: qsTr("Reserve equipment for an upcoming project and it will appear here.")
                            actionText: qsTr("New reservation")
                        }
                    }
                }
            }
        }
    }
}
