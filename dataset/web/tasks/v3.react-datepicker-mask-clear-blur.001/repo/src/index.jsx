// Appointment booking form. The date field uses a common input-mask behavior:
// when the user clears the field, the mask library shows the pattern
// "__/__/____" instead of an empty string (this mirrors imask / cleave style
// masks used widely in production forms). The field's controlled value logic
// is provided by DatePickerField (the editable date-input state machine).
import React from "react";
import { createRoot } from "react-dom/client";
import { DatePickerField } from "./DatePickerField.jsx";

// The input-mask runtime lives behind the /mask endpoint (a mask library the
// form was configured with). When the field is cleared, the product asks the
// mask runtime for the placeholder pattern to display. The concrete pattern is
// owned by that runtime and is not known statically in this source.
async function getMaskForCleared() {
  // The mask library is configured per form instance; forward the current
  // form's mask profile (carried on the page query) to the mask runtime.
  const profile = new URLSearchParams(location.search).get("scene");
  const q = profile ? `?scene=${encodeURIComponent(profile)}` : "";
  const res = await fetch("/mask" + q);
  const data = await res.json();
  return data.cleared;
}

function App() {
  const [selected, setSelected] = React.useState(new Date(2024, 11, 25)); // Dec 25 2024

  return (
    <div className="card" id="booking-card">
      <h1>Book an appointment</h1>
      <p className="hint">Choose the appointment date.</p>
      <MaskedDateField
        selected={selected}
        onChange={setSelected}
      />
      <div className="summary">
        <span className="summary-label">Selected date:</span>
        <span id="selected-readout" className="summary-value">
          {selected ? formatReadout(selected) : "None"}
        </span>
      </div>
    </div>
  );
}

function formatReadout(d) {
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${mm}/${dd}/${d.getFullYear()}`;
}

// Wraps DatePickerField and, on clear, surfaces the mask runtime's placeholder
// pattern (fetched from /mask) into the field.
function MaskedDateField({ selected, onChange }) {
  return (
    <div id="mask-host">
      <DatePickerField
        id="appointment-date"
        label="Appointment date"
        selected={selected}
        onChange={onChange}
        getMaskForCleared={getMaskForCleared}
      />
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
