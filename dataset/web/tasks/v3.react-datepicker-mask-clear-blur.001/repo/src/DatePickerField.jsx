// Behavior-derived clean-room port of the react-datepicker date-input state
// machine (Hacker0x01/react-datepicker src/index.tsx @ base
// 0231bbd7e707d87397e1486d0f2b453cf7f50367). It preserves the EXACT upstream
// decision surface for the input's controlled value across type / change /
// blur, using the real date-fns parse/format helpers. Only the parts that
// participate in the reported blur behavior are reproduced; calendar popper,
// floating-ui, and range/multiple modes are intentionally omitted because they
// are irrelevant to the contract and prohibitively heavy to isolate faithfully.
//
// Upstream flow reproduced verbatim:
//   getInputValue(): if state.inputValue is a string, return it; else format
//                    the currently-`selected` date with dateFormat.
//   handleChange(e): setState({ inputValue: e.target.value }); if the typed
//                    value parses to a valid date, call onChange(date).
//   resetInputValue(): setState({ inputValue: null }).
//   handleBlur(e): resetInputValue(); (upstream also toggles open/focus).
//
// The BROKEN consequence: after the user clears the field to a masked pattern
// like "__/__/____" and blurs, resetInputValue() drops the typed inputValue,
// so getInputValue() falls back to re-formatting the still-`selected` date and
// the field REVERTS to the old date.
import React from "react";
import { parse, format, isValid } from "date-fns";

const DATE_FORMAT = "MM/dd/yyyy";

function safeFormat(date) {
  return date && isValid(date) ? format(date, DATE_FORMAT) : "";
}
function safeParse(value) {
  const d = parse(value, DATE_FORMAT, new Date());
  return isValid(d) && value === safeFormat(d) ? d : null;
}

export function DatePickerField({ selected, onChange, id, label, getMaskForCleared }) {
  const [inputValue, setInputValue] = React.useState(null); // null => derive from `selected`

  // getInputValue(): upstream precedence.
  const value = typeof inputValue === "string" ? inputValue : safeFormat(selected);

  async function handleChange(e) {
    let v = e.target.value;
    // Product-owned input mask: when the user clears the field, the mask
    // library surfaces its placeholder pattern (obtained from the mask
    // runtime) instead of an empty string. The exact pattern is a runtime
    // detail owned by the mask library, not a value known statically here.
    if (v.trim() === "" && typeof getMaskForCleared === "function") {
      const masked = await getMaskForCleared();
      setInputValue(masked);
      return;
    }
    setInputValue(v);
    const parsed = safeParse(v);
    if (parsed) onChange(parsed);
  }

  function resetInputValue() {
    setInputValue(null);
  }

  function handleBlur() {
    // === BROKEN: unconditional reset drops a cleared-mask value, so the field
    // reverts to the old formatted `selected` date. ===
    resetInputValue();
  }

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        autoComplete="off"
        value={value}
        placeholder="MM/DD/YYYY"
        onChange={handleChange}
        onBlur={handleBlur}
      />
    </div>
  );
}
