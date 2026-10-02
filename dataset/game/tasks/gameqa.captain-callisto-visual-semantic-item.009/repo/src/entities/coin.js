
/**
 * The Coin class represents a gold coin that the player can pick up.
 */
class Coin extends GameEntity {
  /**
   * Creates a collectible.
   * @param {number=} x
   * @param {number=} y
   * @param {number=} z
   * @param {{semanticKey: string, semanticUnits: number, visualUnits: number}=} cargo
   */
  constructor(x, y, z, cargo) {
    super(x, y, z);

    /** @type {?Platform} */
    this.carrier = null;

    /** @type {number} */
    this.pickupSequence = 0;

    /** @type {?string} */
    this.semanticKey = cargo ? cargo.semanticKey : null;

    /** @type {number} */
    this.semanticUnits = cargo ? cargo.semanticUnits : 1;

    /** @type {number} */
    this.worldUnits = cargo ? cargo.visualUnits : 1;
  }

  /**
   * Updates the coin.
   * @override
   */
  update() {
    const dist = this.getDistanceToPlayer();
    if (dist < 1.0) {
      this.health = 0;
      const pickupKey = this.semanticKey ||
          'pickup-' + (++this.pickupSequence);
      if (this.carrier) {
        this.carrier.releasePassenger(this);
      }
      recordInventoryReceipt('pickup', pickupKey, this.semanticUnits);
      coinSequence++;
      lastCoinTime = gameTime;
      playCoinSound();
    } else if (dist < 3) {
      // Move the coin toward the player
      this.pos[0] = 0.9 * this.pos[0] + 0.1 * player.pos[0];
      this.pos[1] = 0.9 * this.pos[1] + 0.1 * player.pos[1];
      this.pos[2] = 0.9 * this.pos[2] + 0.1 * player.pos[2];
    }
  }

  /**
   * Renders the coin.
   * @override
   */
  render() {
    const r = (time % 1.0) * 2 * Math.PI;
    const y = 1.5 + 0.2 * Math.sin(r);
    for (let i = 0; i < this.worldUnits; i++) {
      const m = this.createSphere(COLOR_YELLOW);
      const x = (i - (this.worldUnits - 1) / 2) * 0.7;
      mat4.translate(m, m, vec3.fromValues(x, y, 0));
      mat4.rotateY(m, m, r);
      mat4.scale(m, m, vec3.fromValues(0.5, 0.5, 0.1));
    }
  }
}
