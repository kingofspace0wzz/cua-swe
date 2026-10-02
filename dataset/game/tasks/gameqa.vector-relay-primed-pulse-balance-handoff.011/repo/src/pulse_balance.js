(function (global) {
  "use strict";

  function PulseBalance() {}

  PulseBalance.prototype.draw = function (ctx, laneState, commits) {
    var left = 650;
    var top = 36;
    var width = 274;
    var height = 112;
    var totals = [
      Math.max(0, laneState.pending || 0),
      Math.max(0, laneState.withdrawn || 0),
      Math.max(0, commits - 1),
      Math.max(0, laneState.dropped || 0)
    ];
    var labels = ["LIVE", "QUIET", "SEALED", "FRACTURED"];

    ctx.save();
    ctx.fillStyle = "rgba(4, 16, 24, 0.9)";
    ctx.fillRect(left, top, width, height);
    ctx.strokeStyle = "rgba(82, 180, 194, 0.58)";
    ctx.lineWidth = 1;
    ctx.strokeRect(left + 0.5, top + 0.5, width - 1, height - 1);

    ctx.fillStyle = "#8ce6ef";
    ctx.font = "bold 11px Courier New";
    ctx.textAlign = "left";
    ctx.fillText("PULSE BALANCE", left + 14, top + 20);
    ctx.strokeStyle = "rgba(104, 197, 208, 0.2)";
    ctx.beginPath();
    ctx.moveTo(left + 14, top + 29.5);
    ctx.lineTo(left + width - 14, top + 29.5);
    ctx.stroke();

    for (var family = 0; family < totals.length; family += 1) {
      var x = left + 38 + family * 64;
      ctx.fillStyle = "#71949c";
      ctx.font = "8px Courier New";
      ctx.textAlign = "center";
      ctx.fillText(labels[family], x, top + 47);
      for (var mark = 0; mark < totals[family]; mark += 1) {
        var markX = x - 15 + (mark % 3) * 15;
        var markY = top + 67 + Math.floor(mark / 3) * 17;
        if (family === 0) this.drawLive(ctx, markX, markY);
        if (family === 1) this.drawQuiet(ctx, markX, markY);
        if (family === 2) this.drawSealed(ctx, markX, markY);
        if (family === 3) this.drawFractured(ctx, markX, markY);
      }
    }
    ctx.restore();
  };

  PulseBalance.prototype.drawLive = function (ctx, x, y) {
    ctx.strokeStyle = "#64e4ee";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.stroke();
  };

  PulseBalance.prototype.drawQuiet = function (ctx, x, y) {
    ctx.strokeStyle = "#4f91d8";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x - 5, y - 4);
    ctx.lineTo(x, y);
    ctx.lineTo(x + 5, y - 4);
    ctx.moveTo(x - 5, y + 1);
    ctx.lineTo(x, y + 5);
    ctx.lineTo(x + 5, y + 1);
    ctx.stroke();
  };

  PulseBalance.prototype.drawSealed = function (ctx, x, y) {
    ctx.fillStyle = "#e6c85e";
    ctx.beginPath();
    ctx.moveTo(x, y - 6);
    ctx.lineTo(x + 6, y);
    ctx.lineTo(x, y + 6);
    ctx.lineTo(x - 6, y);
    ctx.closePath();
    ctx.fill();
  };

  PulseBalance.prototype.drawFractured = function (ctx, x, y) {
    ctx.strokeStyle = "#db625f";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(x - 6, y - 5);
    ctx.lineTo(x - 2, y - 1);
    ctx.moveTo(x + 1, y - 6);
    ctx.lineTo(x + 4, y - 2);
    ctx.moveTo(x - 1, y + 2);
    ctx.lineTo(x + 5, y + 6);
    ctx.stroke();
  };

  global.PulseBalance = PulseBalance;
}(window));
