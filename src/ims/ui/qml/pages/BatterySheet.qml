import QtQuick
import QtQuick.Controls.Basic
import "../components"

// One battery: cycles, health, what it needs, checks and its cycle ledger.
Sheet {
    id: sheet

    readonly property var d: Batteries.detail
    readonly property bool loaded: d.assetId !== undefined
    property string mode: ""   // "check" | "charge" while entering

    width: Math.min(780, parent ? parent.width - 64 : 780)
    title: loaded ? d.tag + "  ·  " + d.type : qsTr("Loading…")
    subtitle: loaded ? [d.family, d.serial ? qsTr("Serial %1").arg(d.serial) : "", d.chargers ? qsTr("Chargers: %1").arg(d.chargers) : ""]
                       .filter(function (s) { return s }).join("  ·  ") : ""

    function show(assetId) {
        mode = ""
        Batteries.clearError()
        Batteries.openBattery(assetId)
        open()
    }
    onClosed: Batteries.closeBattery()

    Connections {
        target: Batteries
        function onSaved() { sheet.mode = "" }
    }

    component Field: Column {
        property string label: ""
        property string value: ""
        width: 170
        spacing: 2
        Txt { text: parent.label; variant: "caption"; muted: true }
        Txt { text: parent.value || "—"; muted: !parent.value; variant: "headline"; font.features: { "tnum": 1 } }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md
        visible: sheet.loaded

        Row {
            spacing: Theme.space.xs
            StatusPill { kind: sheet.d.conditionKind || "neutral"; text: sheet.d.conditionLabel || "" }
            StatusPill { kind: sheet.d.serviceKind || "neutral"; text: sheet.d.serviceLabel || "" }
        }
        Row {
            spacing: Theme.space.lg
            Field { label: qsTr("Cycles"); value: sheet.d.cyclesText || "" }
            Field { label: sheet.d.measured ? qsTr("Health (measured)") : qsTr("Health"); value: sheet.d.health || "" }
            Field { label: qsTr("Last check"); value: sheet.d.lastCheck || "" }
            Field { label: qsTr("Idle"); value: sheet.d.idle || "" }
        }
        Rectangle {
            width: parent.width
            height: 8
            radius: 4
            color: Theme.colors.element
            Rectangle {
                width: parent.width * (sheet.d.cycleShare || 0)
                height: parent.height
                radius: 4
                color: (sheet.d.cycleShare || 0) >= 1 ? Theme.colors.dangerSolid
                     : (sheet.d.cycleShare || 0) >= 0.9 ? Theme.colors.warningSolid : Theme.colors.accent
                Behavior on width { NumberAnimation { duration: Theme.motion.standard; easing.type: Easing.OutCubic } }
            }
        }
        Repeater {
            model: sheet.d.reasons || []
            delegate: Txt { required property string modelData; width: parent.width; wrapMode: Text.WordWrap; text: "•  " + modelData; color: Theme.colors.dangerText }
        }
        Repeater {
            model: sheet.d.warnings || []
            delegate: Txt { required property string modelData; width: parent.width; wrapMode: Text.WordWrap; text: "•  " + modelData; color: Theme.colors.warningText }
        }

        // ------------------------------------------------------------ record a check
        Column {
            visible: sheet.mode === "check"
            width: parent.width
            spacing: Theme.space.sm
            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Row {
                spacing: Theme.space.md
                AppDatePicker { id: checkDay; width: 180; label: qsTr("Checked on") }
                AppTextField { id: health; width: 120; label: qsTr("Health %") }
                AppTextField { id: resistance; width: 150; label: qsTr("Resistance (mΩ)") }
                AppTextField { id: imbalance; width: 150; label: qsTr("Cell imbalance (mV)") }
            }
            Row {
                spacing: Theme.space.md
                Column {
                    spacing: 6
                    Txt { text: qsTr("Left at"); variant: "caption"; font.weight: Theme.type.medium }
                    AppSelect { id: chargeState; width: 200; model: Batteries.chargeStates; textRole: "label"; valueRole: "value" }
                }
                AppCheckBox { id: swelling; anchors.bottom: parent.bottom; text: qsTr("Swelling") }
                AppCheckBox { id: damage; anchors.bottom: parent.bottom; text: qsTr("Damage") }
            }
            AppTextField { id: checkNotes; width: parent.width; label: swelling.checked || damage.checked ? qsTr("Describe it (required)") : qsTr("Notes (optional)") }
        }

        // ------------------------------------------------------------ charge cycles
        Row {
            visible: sheet.mode === "charge"
            spacing: Theme.space.md
            AppTextField { id: chargeCycles; width: 140; label: qsTr("Charge cycles") }
            AppDatePicker { id: chargeDay; width: 180; label: qsTr("Up to") }
            AppTextField { id: chargeNote; width: 260; label: qsTr("Note (optional)") }
        }

        // ------------------------------------------------------------ history
        Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
        Txt { text: qsTr("Checks"); variant: "headline" }
        Txt { visible: (sheet.d.checks || []).length === 0; text: qsTr("No checks recorded yet."); muted: true }
        Repeater {
            model: sheet.d.checks || []
            delegate: Row {
                required property var modelData
                spacing: Theme.space.md
                Txt { width: 100; text: modelData.when; variant: "caption"; muted: true }
                Txt { width: 60; text: modelData.health; variant: "bodyStrong" }
                Txt { width: 180; text: [modelData.resistance, modelData.imbalance].filter(function (s) { return s }).join(" · ") || "—"; variant: "caption" }
                Txt { width: 120; text: modelData.charge; variant: "caption"; muted: true }
                StatusPill { visible: !!modelData.flag; kind: "danger"; text: modelData.flag }
                Txt { width: 240; text: modelData.notes; variant: "caption"; muted: true; elide: Text.ElideRight }
            }
        }
        Txt { text: qsTr("Cycle ledger"); variant: "headline" }
        Txt { visible: (sheet.d.history || []).length === 0; text: qsTr("No cycles yet."); muted: true }
        Repeater {
            model: sheet.d.history || []
            delegate: Row {
                required property var modelData
                spacing: Theme.space.md
                Txt { width: 100; text: modelData.when; variant: "caption"; muted: true }
                Txt { width: 50; text: modelData.amount; variant: "bodyStrong"; horizontalAlignment: Text.AlignRight; font.features: { "tnum": 1 } }
                Txt { width: 130; text: modelData.source; variant: "caption" }
                Txt { width: 360; text: modelData.note; variant: "caption"; muted: true; elide: Text.ElideRight }
            }
        }
        ErrorBanner { text: Batteries.error }
    }

    actions: [
        AppButton { text: sheet.mode ? qsTr("Back") : qsTr("Close"); onClicked: sheet.mode ? sheet.mode = "" : sheet.close() },
        AppButton {
            visible: sheet.loaded && Batteries.canRecord && !sheet.mode && !sheet.d.isDroneBattery
            text: qsTr("Log charge cycles…")
            onClicked: { sheet.mode = "charge"; chargeCycles.text = ""; chargeNote.text = ""
                         chargeDay.hasDate = true; chargeDay.selectedDate = new Date() }
        },
        AppButton {
            visible: sheet.loaded && Batteries.canRecord && !sheet.mode
            variant: "primary"
            text: qsTr("Record check…")
            onClicked: { sheet.mode = "check"; health.text = ""; resistance.text = ""; imbalance.text = ""
                         checkNotes.text = ""; swelling.checked = false; damage.checked = false; chargeState.currentIndex = 0
                         checkDay.hasDate = true; checkDay.selectedDate = new Date() }
        },
        AppButton {
            visible: sheet.mode === "check"
            variant: swelling.checked || damage.checked ? "danger" : "primary"
            text: qsTr("Save check")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: Batteries.recordCheck(sheet.d.assetId, {
                checkedOn: Qt.formatDate(checkDay.selectedDate, "yyyy-MM-dd"), health: health.text,
                resistance: resistance.text, imbalance: imbalance.text, swelling: swelling.checked,
                damage: damage.checked, chargeState: chargeState.currentValue, notes: checkNotes.text
            })
        },
        AppButton {
            visible: sheet.mode === "charge"
            variant: "primary"
            text: qsTr("Log cycles")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: Batteries.logCharge(sheet.d.assetId, chargeCycles.text, Qt.formatDate(chargeDay.selectedDate, "yyyy-MM-dd"), chargeNote.text)
        }
    ]
}
