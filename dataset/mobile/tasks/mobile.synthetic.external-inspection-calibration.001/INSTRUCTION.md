# Repair imported inspection measurements

Fieldline's imported inspection workflow is displaying misplaced annotation endpoints and unreliable lengths. Repair the client interpretation so annotations and measurements agree with the provider's inspection attachment and calibration/report, including after an endpoint edit. Keep note editing (Save and Cancel), record switching, and ordinary reload working without losing saved edits or modifying provider originals.

Start in the inspection, compare **Annotation** with **Original**, and open **Report** (including its **Payload** view). **Inbox** opens the other imported inspection. The provider evidence explains the intended interpretation; the symptom alone is not the specification. Support both imported records and other records following the same observable provider contract, not fixed displayed answers.

This is an original standalone synthetic mobile web app, not a native Android/iOS app. The prepared runtime imports external provider records into its isolated browser profile. Ordinary startup outside that runtime has an empty inbox; no missing source file needs to be obtained. The same provider inputs are present in both task conditions. Ordinary reload preserves user data and does not import again. A source rebuild explicitly resets to the initial imported scene.

All ordinary client source and build inputs are provided. You may edit every ordinary client file except the protected build.sh wrapper. No dependencies are needed. Run `sh build.sh` for the public syntax/build check. Use the existing mobile runtime for app observation when available.
