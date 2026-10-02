#!/usr/bin/env node

import {mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';

globalThis.requestAnimationFrame = () => 0;

const {Game} = await import('../src/game.js');
const artifactRoot = process.env.CUA_SWE_VERIFIER_ARTIFACTS || 'verifier-artifacts';
const checks = [];
const checkpoints = {};

function close(actual, expected, tolerance = 0.02) {
  return Math.abs(Number(actual) - expected) <= tolerance;
}

function check(name, passed, detail) {
  checks.push({name, passed: Boolean(passed), detail});
}

function contextStub() {
  const gradient = {addColorStop() {}};
  return {
    clearRect() {}, createRadialGradient() { return gradient; }, fillRect() {},
    beginPath() {}, arc() {}, stroke() {}, moveTo() {}, lineTo() {}, fill() {},
    save() {}, translate() {}, rotate() {}, restore() {}, fillText() {},
  };
}

const canvas = {getContext() { return contextStub(); }};
const ui = {
  showReady() {}, hideOverlay() {}, setStatus() {}, showFailure() {},
  showPass() {}, update() {},
};
const game = new Game(canvas, ui);

function state(name) {
  const value = game.getState();
  checkpoints[name] = value;
  return value;
}

game.reset({seed: 808, level: 1, manual: true});
game.start();
game.fire();
game.advance(7000);
game.fire();
const queued = state('queue_window');
check(
  'ordinary_coordinate_queue_window',
  queued.round.phase === 'playing'
    && queued.shots.waiting === 1
    && queued.shots.active.progress > 0.3
    && queued.shots.active.progress < 0.4
    && queued.metrics.inputs === 2
    && close(queued.motion.angle, 252),
  queued,
);

game.advance(12000);
const beforeFirst = state('pre_first_contact');
check(
  'long_visible_first_flight_preserves_queue',
  beforeFirst.round.phase === 'playing'
    && beforeFirst.metrics.attachments === 0
    && beforeFirst.shots.waiting === 1
    && close(beforeFirst.shots.active.progress, 0.95)
    && close(beforeFirst.motion.angle, 324)
    && JSON.stringify(beforeFirst.occupancy.pins) === JSON.stringify([180, 300, 359]),
  beforeFirst,
);

game.advance(1000);
const first = state('first_attachment_commit');
const promotedAfterCommit = first.round.phase === 'playing'
  && first.metrics.attachments === 1
  && first.round.remaining === 3
  && first.motion.transition.active
  && first.shots.waiting === 0
  && first.shots.active !== null
  && first.shots.active.launchProfile === 'shifting'
  && first.shots.active.flightTime === 710
  && close(first.lastAttachment.localAngle, 90);
check('waiting_shot_promoted_from_committed_pace', promotedAfterCommit, first);

game.advance(700);
const approach = state('second_approach');
check(
  'visible_followup_approaches_open_gap',
  approach.round.phase === 'playing'
    && approach.metrics.attachments === 1
    && approach.shots.active !== null
    && approach.shots.active.progress > 0.9
    && close(approach.motion.angle, 58.275)
    && approach.metrics.failures === 0,
  approach,
);

game.advance(80);
const after = state('post_trigger');
const aligned = promotedAfterCommit
  && after.round.phase === 'playing'
  && after.metrics.attachments === 2
  && after.metrics.failures === 0
  && after.round.remaining === 2
  && close(after.scenario.timeMs, 20780)
  && close(after.motion.angle, 69.147)
  && close(after.lastAttachment.at, 20710)
  && close(after.lastAttachment.coreAngle, 59.58675)
  && close(after.lastAttachment.localAngle, 30.41325)
  && after.lastAttachment.launchProfile === 'shifting'
  && close(
    (after.lastAttachment.localAngle + after.lastAttachment.coreAngle) % 360,
    after.lastAttachment.worldAngle,
  );
check('post_commit_promotion_transaction', aligned, after);

if (aligned) {
  const attachedAngles = [...after.occupancy.pins];
  game.advance(1220);
  const persisted = state('post_transition_persistence');
  check(
    'attachment_persists_through_pace_change',
    persisted.round.phase === 'playing'
      && JSON.stringify(persisted.occupancy.pins) === JSON.stringify(attachedAngles)
      && !persisted.motion.transition.active
      && close(persisted.scenario.timeMs, 22000),
    persisted,
  );

  game.fire();
  game.advance(600);
  const third = state('third_attachment');
  check(
    'ordinary_spaced_shot_after_transition',
    third.round.phase === 'playing'
      && third.metrics.attachments === 3
      && third.lastAttachment.launchProfile === 'sprint'
      && close(third.lastAttachment.localAngle, 118.8),
    third,
  );

  game.advance(1000);
  game.fire();
  game.advance(600);
  const completed = state('completed');
  check(
    'normal_round_completion',
    completed.round.phase === 'passed'
      && completed.round.remaining === 0
      && completed.metrics.attachments === 4
      && completed.metrics.completed === 1
      && close(completed.lastAttachment.localAngle, 248.4),
    completed,
  );
} else {
  for (const name of [
    'attachment_persists_through_pace_change',
    'ordinary_spaced_shot_after_transition',
    'normal_round_completion',
  ]) check(name, false, 'post-trigger contract failed');
}

const restarted = game.reset({seed: 808, level: 1, manual: true});
checkpoints.restart_before_collision_probe = restarted;
check(
  'restart_clears_round_occupancy_and_motion',
  JSON.stringify(restarted.round) === JSON.stringify({phase: 'ready', remaining: 4})
    && JSON.stringify(restarted.occupancy.pins) === JSON.stringify([180, 300, 359])
    && JSON.stringify(restarted.metrics) === JSON.stringify({inputs: 0, attachments: 0, failures: 0, completed: 0})
    && !restarted.motion.transition.active,
  restarted,
);

game.start();
game.advance(2500);
game.fire();
game.advance(20000);
const rejected = state('rejected_attachment_transaction');
check(
  'rejected_collision_is_not_committed',
  rejected.round.phase === 'failed'
    && rejected.metrics.failures === 1
    && rejected.metrics.attachments === 0
    && rejected.lastAttachment.accepted === false
    && JSON.stringify(rejected.occupancy.pins) === JSON.stringify([180, 300, 359]),
  rejected,
);

const finalRestart = game.reset({seed: 808, level: 1, manual: true});
checkpoints.final_restart = finalRestart;
check(
  'restart_remains_normal_after_rejected_collision',
  JSON.stringify(finalRestart.round) === JSON.stringify({phase: 'ready', remaining: 4})
    && JSON.stringify(finalRestart.occupancy.pins) === JSON.stringify([180, 300, 359])
    && JSON.stringify(finalRestart.metrics) === JSON.stringify({inputs: 0, attachments: 0, failures: 0, completed: 0}),
  finalRestart,
);

const report = {
  checks,
  checkpoints,
  success: checks.length > 0 && checks.every((item) => item.passed),
};
await mkdir(artifactRoot, {recursive: true});
await writeFile(path.join(artifactRoot, 'module-replay.json'), `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.success ? 0 : 1;
