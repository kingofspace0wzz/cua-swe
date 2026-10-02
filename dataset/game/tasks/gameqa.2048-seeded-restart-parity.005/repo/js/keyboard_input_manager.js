function KeyboardInputManager() {
  this.events = {};
  this.down = {};
  this.pending = null;
  this.serial = 0;
  this.listen();
}

KeyboardInputManager.prototype.on = function (event, callback) {
  if (!this.events[event]) this.events[event] = [];
  this.events[event].push(callback);
};

KeyboardInputManager.prototype.emit = function (event, data) {
  var callbacks = this.events[event];
  if (callbacks) callbacks.forEach(function (callback) { callback(data); });
};

KeyboardInputManager.prototype.listen = function () {
  var self = this;
  var map = { 38: 0, 39: 1, 40: 2, 37: 3, 75: 0, 76: 1, 74: 2, 72: 3 };

  document.addEventListener("keydown", function (event) {
    var modifiers = event.altKey || event.ctrlKey || event.metaKey || event.shiftKey;
    var direction = map[event.which];
    if (modifiers) return;

    if (direction !== undefined) {
      event.preventDefault();
      if (self.down[direction]) return;
      self.down[direction] = true;
      self.emit("move", direction);
      var serial = ++self.serial;
      self.pending = window.setTimeout(function () {
        if (self.down[direction] && serial === self.serial) {
          self.emit("move", direction);
        }
      }, 260);
    }

    if (event.which === 32) self.restart(event);
  });

  document.addEventListener("keyup", function (event) {
    var direction = map[event.which];
    if (direction === undefined) return;
    delete self.down[direction];
    self.serial += 1;
    if (self.pending !== null) {
      window.clearTimeout(self.pending);
      self.pending = null;
    }
  });

  document.getElementsByClassName("retry-button")[0]
    .addEventListener("click", this.restart.bind(this));

  var directions = [
    Hammer.DIRECTION_UP,
    Hammer.DIRECTION_RIGHT,
    Hammer.DIRECTION_DOWN,
    Hammer.DIRECTION_LEFT
  ];
  Hammer(document.getElementsByClassName("game-container")[0], {
    drag_block_horizontal: true,
    drag_block_vertical: true
  }).on("swipe", function (event) {
    event.gesture.preventDefault();
    var direction = directions.indexOf(event.gesture.direction);
    if (direction !== -1) self.emit("move", direction);
  });
};

KeyboardInputManager.prototype.restart = function (event) {
  event.preventDefault();
  this.emit("restart");
};
