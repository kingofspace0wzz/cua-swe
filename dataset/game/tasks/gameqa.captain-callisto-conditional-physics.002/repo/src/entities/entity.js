
/**
 * The GameEntity class represents an entity in the game.
 */
class GameEntity {
  /**
   * Creates a new game entity.
   * @param {number=} x
   * @param {number=} y
   * @param {number=} z
   */
  constructor(x, y, z) {
    /** @const {!vec3} */
    this.pos = vec3.fromValues(x || 0, y || 0, z || 0);

    /** @const {!vec3} */
    this.velocity = vec3.create();

    /** @const {!vec3} */
    this.interactionStart = vec3.clone(this.pos);

    /** @const {!vec3} */
    this.interactionEnd = vec3.clone(this.pos);

    /** @const {!mat4} */
    this.transformMatrix = mat4.create();

    /** @type {number} */
    this.health = 100;

    /** @type {number} */
    this.yaw = 0;

    /** @type {boolean} */
    this.accelerating = false;

    /** @type {number} */
    this.groundedTime = 0;

    /** @type {?Platform} */
    this.groundedPlatform = null;

    /** @type {number} */
    this.shootTime = 0;

    /** @type {number} */
    this.bounciness = 0.0;

    /** @type {!Array.<!vec3>} */
    this.waypoints = [];

    /** @type {number} */
    this.waypointIndex = 0;

    /** @type {boolean} */
    this.rendered = true;

    /** @type {string} */
    this.debugLabel = '';
  }

  /**
   * Returns true if the entity is on the ground.
   * @return {boolean}
   */
  isGrounded() {
    return this.groundedTime === gameTime;
  }

  /**
   * Returns true if the entity can jump.
   * @return {boolean}
   */
  canShoot() {
    return (gameTime - this.shootTime) > 0.5;
  }

  /**
   * Launches the player.
   */
  jump() {
    this.velocity[1] = JUMP_POWER;
    this.groundedTime = 0;
    this.groundedPlatform = null;
    if (this === player) {
      playJumpSound();
    }
  }

  /**
   * Updates the entity.
   * By default, does nothing.
   */
  update() {
    // Subclasses should override
  }

  /**
   * Renders the entity.
   * By default, does nothing.
   * Static entities can use this default implementation.
   */
  render() {
    // Subclasses should override
  }

  /**
   * Returns the distance to the player.
   * @return {number} Distance to the player.
   */
  getDistanceToPlayer() {
    if (player.health <= 0) {
      return 1000;
    }
    return vec3.distance(player.pos, this.pos);
  }

  /** Begins the motion span used by frame-local interactions. */
  beginInteractionFrame() {
    vec3.copy(this.interactionStart, this.pos);
    vec3.copy(this.interactionEnd, this.pos);
  }

  /** Seals the motion span used by frame-local interactions. */
  endInteractionFrame() {
    vec3.copy(this.interactionEnd, this.pos);
  }

  /**
   * Returns the shortest distance from this entity to the player's frame span.
   * @return {number}
   */
  getDistanceToPlayerPath() {
    if (player.health <= 0) {
      return 1000;
    }
    const start = player.interactionStart;
    const end = player.interactionEnd;
    const dx = end[0] - start[0];
    const dy = end[1] - start[1];
    const dz = end[2] - start[2];
    const lengthSquared = dx * dx + dy * dy + dz * dz;
    const projection = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1,
        ((this.pos[0] - start[0]) * dx +
         (this.pos[1] - start[1]) * dy +
         (this.pos[2] - start[2]) * dz) / lengthSquared));
    const closestX = start[0] + projection * dx;
    const closestY = start[1] + projection * dy;
    const closestZ = start[2] + projection * dz;
    return Math.hypot(
        this.pos[0] - closestX,
        this.pos[1] - closestY,
        this.pos[2] - closestZ);
  }

  /**
   * Updates waypoints.
   * Silently ignores if no waypoints are setup.
   * @return {?vec3} The current waypoint if available.
   */
  updateWaypoints() {
    if (this.waypoints.length === 0) {
      return null;
    }
    const waypoint = this.waypoints[this.waypointIndex];
    if (vec3.distance(this.pos, waypoint) < 0.1) {
      this.waypointIndex = (this.waypointIndex + 1) % this.waypoints.length;
    }
    return waypoint;
  }

  /**
   * Sets up the default transform matrix.
   */
  setupTransformMatrix() {
    const theta = time * 20;
    const speed = Math.hypot(this.velocity[0], this.velocity[2]);
    const bodyOffsetY = this.bounciness * Math.sin(theta) * speed;
    const bodyRotationX = 0.02 * speed;

    vec3.copy(tempVec, this.pos);

    if (this.isGrounded()) {
      tempVec[1] += bodyOffsetY;
    }

    mat4.identity(this.transformMatrix);
    mat4.translate(this.transformMatrix, this.transformMatrix, tempVec);
    mat4.rotateY(this.transformMatrix, this.transformMatrix, this.yaw);
    mat4.rotateX(this.transformMatrix, this.transformMatrix, bodyRotationX);
  }

  /**
   * Creates a new sphere transformed to instance space.
   * @param {number} color
   * @return {!mat4}
   */
  createSphere(color) {
    const m = buffers[DYNAMIC_SPHERES].addInstance(color);
    mat4.multiply(m, m, this.transformMatrix);
    return m;
  }
}
