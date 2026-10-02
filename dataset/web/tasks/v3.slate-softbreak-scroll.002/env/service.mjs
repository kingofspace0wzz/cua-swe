import http from 'node:http';

// Harness-owned workspace frame service for the Field Log Composer.
//
// A field log opens inside a workspace frame. The frame reserves a band at the
// top for its pinned action bar and a band at the bottom for its status strip;
// the log's scrollable body is whatever remains between them. Each workspace
// reserves different bands and opens at a different overall height, and each
// carries a starting log body long enough that the writing surface is already
// full when the composer opens. Each workspace also fixes its own text scale,
// so a single soft-break line occupies a different height on each frame.
//
// The service hands the composer only the frame dimensions and the log body.
// It never hands over any resolved scroll position, delta, or the caret's
// intended resting coordinate; those are runtime layout facts the product must
// derive on its own from the live surface.

const args = process.argv.slice(2);
const port = Number((args.includes('--port') ? args[args.indexOf('--port') + 1] : 0) || 4430);
const host = (args.includes('--host') ? args[args.indexOf('--host') + 1] : '') || '127.0.0.1';
const variant = process.env.CONTRACT_VARIANT || 'a';

// Three protected workspace frames. Each fixes an action-bar band at the top,
// a status-strip band at the bottom, an overall frame height, and a text
// scale; the body is long enough to overflow every frame so the caret starts
// near the bottom.
const frames = {
  a: {
    workspace: 'Site inspection log',
    title: 'North corridor walkthrough',
    frame: { height: 460, topBand: 52, bottomBand: 40 },
    fontScale: 0.72,
    caretBlock: 8,
    body: [
      'Arrived on site just after nine and signed in at the trailer, then met the foreman by the north gate to walk the plan for the day before the crew fanned out to their stations.',
      'Walked the north corridor end to end before the crew started work, checking the fire doors, the exit signage, and the floor markings against the last inspection sheet as I went.',
      'The east stairwell handrail is loose near the third landing and the paint has started flaking along the lower rail where people grip it on the way down toward the service level.',
      'Loading dock seal looks compromised on the left roller where the rubber has torn back, and the two ceiling tiles in the west bay are water stained again after last week rain.',
      'Fire extinguisher tag in room 12 is past its inspection date, and the emergency lighting in the rear passage did not test cleanly when I held the button through a full cycle.',
      'The dock leveler on bay two is slow to seat and clunks on the way down, which the receiving lead says has been getting worse over the past couple of weeks.',
      'Checked the roof access ladder cage and found one anchor bolt backed out most of the way, so I flagged it as a priority before anyone goes up for the seasonal work.',
      'Perimeter fence gate at the north drive does not latch on its own and swings in the wind, and the motion light above it did not come on when I crossed the sensor.',
      'Requested the contractor revisit the handrail before Friday and flagged the dock seal for the maintenance queue so the receiving team is not surprised on the next delivery.',
      'Left a copy of the marked floor plan with the foreman and walked the punch list with him before I packed up.',
      'Closing note: crew cleared the corridor by end of shift and staged their tools against the east wall.',
    ],
  },
  b: {
    workspace: 'Incident report',
    title: 'Line 3 stoppage',
    frame: { height: 380, topBand: 44, bottomBand: 56 },
    fontScale: 1.0,
    caretBlock: 9,
    body: [
      'Line 3 stopped at the capper station during second shift when a jam alarm sounded and the belt cut out before the operator could reach the reset button on the near panel.',
      'The operator reported the jam alarm came in about a second before the belt cut out, and by the time she looked up the accumulation table behind the capper had already backed up.',
      'Maintenance found a bottle wedged under the transfer guard where the rail steps down, and once it was cleared the station cycled three times clean with no further alarms on the line.',
      'The upstream filler kept running for a few seconds after the stop, so a short row of bottles bunched at the dead plate and two of them tipped against the guard rail.',
      'We walked the section back to the filler with the line lead and did not find any other obstructions or damaged rollers along the transfer that would explain the wedge.',
      'Quality held the bottles from the affected window and inspected them for chipping before releasing the good ones back to the accumulation table for the restart.',
      'The reset sequence needed two attempts because the guard interlock did not clear the first time until the guard was reseated fully into its bracket.',
      'Downtime was logged as twenty two minutes against the shift total, and the affected bottles were pulled to the rework bin and counted back into inventory by the line lead.',
      'Recommend adding a guard position check to the startup list so the next crew confirms the transfer guard is seated before they bring the capper up to full speed on a fresh run.',
      'Also recommend a quick look at the dead plate gap, since the bunching suggests it may be a touch wide for the current bottle size.',
      'No injuries and no product loss from the stoppage; the supervisor signed off and restarted the line at capacity.',
    ],
  },
  c: {
    workspace: 'Field service note',
    title: 'Rooftop unit callback',
    frame: { height: 540, topBand: 60, bottomBand: 48 },
    fontScale: 1.42,
    caretBlock: 9,
    body: [
      'Callback on the rooftop unit that tripped over the weekend; the building engineer met me at the roof hatch and walked me over to the unit that had faulted on the front panel.',
      'Found the condenser fan drawing high amps on startup, and when I pulled the guard the bearings were dry and the blade showed an early wobble that got worse as the motor spun up.',
      'The contactor showed some pitting on the line side and the disconnect fuses tested fine, so the high amps pointed at the motor rather than the supply side of the circuit.',
      'Replaced the motor with the stocked spare and rebalanced the blade, then verified the refrigerant charge against the nameplate values before closing the unit back up for a test run.',
      'Swapped the pitted contactor while I had the panel open since it was already showing wear and would likely have been the next thing to fail on this unit.',
      'Checked the economizer damper linkage because the logs showed it hunting, and found the actuator arm slightly loose on its shaft, which I snugged and re-tested.',
      'Cleaned the condenser coil face while I was on the roof because it was packed with cottonwood and would have driven head pressure up on the next hot day.',
      'Cycled the unit through two full cooling calls on the roof and watched the amp draw settle well inside the service factor after the swap, which lines up with what the nameplate expects.',
      'Confirmed the space thermostat was calling correctly and that the unit staged as expected without short cycling across the two calls I ran.',
      'Left the old motor tagged for warranty return in the van and noted the serial on the service ticket so the office can open the claim with the manufacturer before the window closes.',
      'Customer confirmed the space was holding setpoint on the way out and asked to be on the list for the seasonal maintenance visit.',
    ],
  },
};
const payload = frames[variant] || frames.a;

http.createServer((req, res) => {
  res.setHeader('content-type', 'application/json');
  if (req.url === '/health') { res.end('{"ok":true}'); return; }
  if (req.url === '/api/composer-frame') { res.end(JSON.stringify(payload)); return; }
  res.statusCode = 404; res.end('{"error":"not found"}');
}).listen(port, host);
