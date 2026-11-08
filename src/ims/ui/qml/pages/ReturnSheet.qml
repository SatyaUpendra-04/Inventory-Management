import QtQuick
import QtQuick.Controls.Basic
import "../components"

// A deployment: what went out, and the return of each item with its condition.
Sheet {
    id: sheet

    readonly property var d: Deployments.detail
    readonly property bool loaded: d.deploymentId !== undefined
    readonly property bool returning: loaded && d.canReturn && Deployments.canReturn
    property var conditions: ({})   // assetId -> condition
    property var notes: ({})        // assetId -> note

    width: Math.min(780, parent ? parent.width - 64 : 780)
    title: loaded ? (returning ? qsTr("Return equipment") : qsTr("Deployment")) : qsTr("Loading…")
    subtitle: loaded ? d.project + "  ·  " + qsTr("out %1").arg(d.deployedOn)
                       + (d.returnedOn ? qsTr(", back %1").arg(d.returnedOn) : "") : ""

    function show(deploymentId) {
        Deployments.clearError()
        conditions = ({}); notes = ({})
        gcpBack.text = ""
        returnDay.hasDate = true; returnDay.selectedDate = new Date()
        Deployments.loadChoices()
        Deployments.openDeployment(deploymentId)
        open()
    }
    function setCondition(assetId, value) { var c = Object.assign({}, conditions); c[assetId] = value; conditions = c }
    function setNote(assetId, value) { var n = Object.assign({}, notes); n[assetId] = value; notes = n }
    function values() {
        var lines = (d.items || []).map(function (item) {
            return { assetId: item.assetId, condition: conditions[item.assetId] || "ok", note: notes[item.assetId] || "" }
        })
        return {
            lines: lines, gcpIssued: String(d.gcp || 0), gcpReturned: gcpBack.text || "0",
            returnSiteId: returnStore.currentValue || "",
            returnedOn: returnDay.hasDate ? Qt.formatDate(returnDay.selectedDate, "yyyy-MM-dd") : ""
        }
    }
    function presetStore() { if (loaded) returnStore.selectValue(d.gcpSiteId || "") }
    onDChanged: Qt.callLater(presetStore)
    Connections { target: Deployments; function onChoicesChanged() { Qt.callLater(sheet.presetStore) } }
    readonly property int gcpUsed: Math.max(0, (d.gcp || 0) - (parseInt(gcpBack.text) || 0))

    Connections {
        target: Deployments
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md
        visible: sheet.loaded

        Row {
            spacing: Theme.space.xs
            StatusPill { kind: sheet.d.stateKind || "neutral"; text: sheet.d.stateLabel || "" }
            Txt { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Crew: %1").arg(sheet.d.crew || ""); muted: true }
        }
        Txt { visible: !!sheet.d.failure; width: parent.width; text: sheet.d.failure || ""; color: Theme.colors.dangerText; wrapMode: Text.WordWrap }

        Repeater {
            model: sheet.d.items || []
            delegate: Rectangle {
                required property var modelData
                readonly property string condition: sheet.conditions[modelData.assetId] || "ok"
                width: parent.width
                height: line.implicitHeight + Theme.space.sm * 2
                radius: Theme.radius.sm
                color: Theme.colors.element
                Column {
                    id: line
                    x: Theme.space.sm
                    y: Theme.space.sm
                    width: parent.width - Theme.space.sm * 2
                    spacing: Theme.space.xs
                    Item {
                        width: parent.width
                        height: 34
                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: Theme.space.md
                            Txt { width: 96; text: modelData.tag; variant: "bodyStrong" }
                            Txt { width: 200; text: modelData.type; elide: Text.ElideRight }
                            StatusPill { kind: modelData.serviceKind; text: modelData.serviceLabel }
                        }
                        AppSelect {
                            visible: sheet.returning
                            anchors.right: parent.right
                            width: 230
                            model: Deployments.conditions
                            textRole: "label"
                            valueRole: "value"
                            onActivated: sheet.setCondition(modelData.assetId, currentValue)
                        }
                        Txt {
                            visible: !sheet.returning && !!modelData.returned
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.returned === "ok" ? qsTr("Returned OK")
                                  : modelData.returned === "limited" ? qsTr("Returned with a defect") : qsTr("Returned damaged")
                            color: modelData.returned === "ok" ? Theme.colors.successText : Theme.colors.warningText
                        }
                    }
                    AppTextField {
                        visible: sheet.returning && parent.parent.condition !== "ok"
                        width: parent.width
                        placeholder: qsTr("Describe the defect or damage (required)")
                        onTextChanged: sheet.setNote(modelData.assetId, text)
                    }
                    Txt { visible: !sheet.returning && !!modelData.returnNote; text: modelData.returnNote; muted: true; variant: "caption" }
                }
            }
        }

        // ------------------------------------------------------------ GCP banners
        Column {
            visible: (sheet.d.gcp || 0) > 0
            width: parent.width
            spacing: Theme.space.xs
            Txt { text: qsTr("GCP banners: %1 issued from %2").arg(sheet.d.gcp || 0).arg(sheet.d.gcpFrom || ""); variant: "bodyStrong" }
            Row {
                visible: sheet.returning
                spacing: Theme.space.md
                AppTextField { id: gcpBack; width: 140; label: qsTr("Brought back") }
                Column {
                    width: 300
                    spacing: 6
                    Txt { text: qsTr("Returned to"); variant: "caption"; font.weight: Theme.type.medium }
                    AppSelect {
                        id: returnStore
                        width: parent.width
                        model: (Deployments.choices.sites || [])
                        textRole: "label"
                        valueRole: "value"
                    }
                }
                Txt { anchors.bottom: parent.bottom; bottomPadding: 8; text: qsTr("Used or left on site: %1").arg(sheet.gcpUsed); muted: true }
            }
            Txt { visible: !sheet.returning && sheet.d.state === "returned"
                  text: qsTr("%1 brought back, %2 used or left on site").arg(sheet.d.gcpReturned || 0).arg(sheet.d.gcpConsumed || 0); muted: true }
        }
        AppDatePicker { id: returnDay; visible: sheet.returning; width: 220; label: qsTr("Returned on") }
        ErrorBanner { text: Deployments.error }
    }

    actions: [
        AppButton { text: sheet.returning ? qsTr("Cancel") : qsTr("Close"); onClicked: sheet.close() },
        AppButton {
            visible: sheet.returning
            variant: "primary"
            text: qsTr("Return everything")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: Deployments.returnEquipment(sheet.d.deploymentId, sheet.d.version, sheet.values())
        }
    ]
}
