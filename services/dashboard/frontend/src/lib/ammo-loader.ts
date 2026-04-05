/**
 * Async singleton loader for ammo.js (Bullet physics engine).
 * Sets globalThis.Ammo so that three-stdlib's MMDPhysics can find it.
 */

let promise: Promise<boolean> | null = null;

async function loadAmmo(): Promise<boolean> {
  try {
    const AmmoModule = await import('ammo.js');
    const Ammo = AmmoModule.default ?? AmmoModule;
    // ammo.js factory returns the initialized module
    const instance = typeof Ammo === 'function' ? Ammo() : Ammo;
    (globalThis as any).Ammo = instance;
    console.log('[ammo-loader] Ammo.js initialized');
    return true;
  } catch (e) {
    console.warn('[ammo-loader] Failed to load ammo.js, physics disabled:', e);
    return false;
  }
}

export function initAmmo(): Promise<boolean> {
  if (!promise) {
    promise = loadAmmo();
  }
  return promise;
}

export function isAmmoReady(): boolean {
  return typeof (globalThis as any).Ammo !== 'undefined';
}
